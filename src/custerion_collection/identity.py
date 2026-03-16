from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlencode

from custerion_collection.models import FilmIdentity
from custerion_collection.tools import _http_get_json


@dataclass(frozen=True)
class IdentityResolutionResult:
    identity: FilmIdentity | None
    error: str | None = None


def resolve_canonical_film_identity(title: str) -> IdentityResolutionResult:
    """Resolve a title to a canonical TMDb-backed identity or return an actionable error."""
    api_key = os.getenv("TMDB_API_KEY", "").strip()
    if not api_key:
        return IdentityResolutionResult(
            identity=None,
            error=(
                "Canonical identity resolution requires TMDB_API_KEY. "
                "Set TMDB_API_KEY or run with --dry-run for offline smoke checks."
            ),
        )

    parsed_title, parsed_year = _parse_title_year(title)
    params: dict[str, str] = {
        "api_key": api_key,
        "query": parsed_title,
        "include_adult": "false",
        "page": "1",
    }
    if parsed_year is not None:
        params["year"] = str(parsed_year)

    search_url = "https://api.themoviedb.org/3/search/movie?" + urlencode(params)
    payload, error = _http_get_json(search_url)
    if error:
        return IdentityResolutionResult(identity=None, error=f"Canonical identity lookup failed: {error}.")

    results = (payload or {}).get("results", [])
    if not results:
        return IdentityResolutionResult(identity=None, error=f"No canonical match found for '{title}'.")

    candidate = _choose_candidate(parsed_title=parsed_title, parsed_year=parsed_year, results=results)
    if candidate is None:
        options = ", ".join(_format_candidate(item) for item in results[:3])
        return IdentityResolutionResult(
            identity=None,
            error=(
                f"Ambiguous title '{title}'. Provide year in the title (example: '{parsed_title} (YEAR)'). "
                f"Top matches: {options}."
            ),
        )

    movie_id = candidate.get("id")
    details = {}
    if movie_id is not None:
        details_url = "https://api.themoviedb.org/3/movie/" + str(movie_id) + "?" + urlencode({
            "api_key": api_key,
            "append_to_response": "credits,external_ids",
        })
        details, _details_error = _http_get_json(details_url)

    base = details or candidate
    release_date = str(base.get("release_date") or candidate.get("release_date") or "")
    release_year = _parse_release_year(release_date) or parsed_year or 0
    tmdb_id = str(base.get("id") or candidate.get("id") or "")
    imdb_id = str(((base.get("external_ids") or {}).get("imdb_id") or "")).strip()

    credits = (base.get("credits") or {}).get("crew") or []
    director = next((entry.get("name") for entry in credits if entry.get("job") == "Director" and entry.get("name")), None)
    key_credits = [director] if director else []

    external_ids: dict[str, str] = {}
    if tmdb_id:
        external_ids["tmdb"] = tmdb_id
    if imdb_id:
        external_ids["imdb"] = imdb_id

    identity = FilmIdentity(
        title=str(base.get("title") or candidate.get("title") or parsed_title).strip(),
        year=release_year,
        key_credits=key_credits,
        runtime_minutes=base.get("runtime"),
        language=base.get("original_language"),
        canonical_id=f"tmdb:movie:{tmdb_id}" if tmdb_id else f"title:{parsed_title}:{release_year}",
        external_ids=external_ids,
    )
    return IdentityResolutionResult(identity=identity, error=None)


def _parse_title_year(raw_title: str) -> tuple[str, int | None]:
    match = re.match(r"^(?P<title>.+?)\s*\((?P<year>\d{4})\)$", raw_title.strip())
    if not match:
        return raw_title.strip(), None
    return match.group("title").strip(), int(match.group("year"))


def _parse_release_year(release_date: str) -> int | None:
    if len(release_date) < 4:
        return None
    head = release_date[:4]
    if not head.isdigit():
        return None
    return int(head)


def _choose_candidate(parsed_title: str, parsed_year: int | None, results: list[dict]) -> dict | None:
    if not results:
        return None

    if parsed_year is not None:
        same_year = [item for item in results if _parse_release_year(str(item.get("release_date") or "")) == parsed_year]
        if len(same_year) == 1:
            return same_year[0]
        if len(same_year) > 1:
            exact_title = [
                item
                for item in same_year
                if str(item.get("title") or "").strip().lower() == parsed_title.lower()
            ]
            if len(exact_title) == 1:
                return exact_title[0]
            return None

    exact_title_all = [
        item for item in results if str(item.get("title") or "").strip().lower() == parsed_title.lower()
    ]
    if len(exact_title_all) == 1:
        return exact_title_all[0]
    if len(exact_title_all) > 1:
        return None

    if len(results) == 1:
        return results[0]
    return None


def _format_candidate(item: dict) -> str:
    title = str(item.get("title") or "Unknown")
    year = _parse_release_year(str(item.get("release_date") or ""))
    if year is None:
        return title
    return f"{title} ({year})"
