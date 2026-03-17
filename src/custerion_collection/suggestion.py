from __future__ import annotations

import os
from urllib.parse import quote, urlencode

from custerion_collection.tools import _http_get_json


def suggest_film_title() -> tuple[str, list[str]]:
    """Return a concrete suggested title using approved providers.

    Priority:
    1. TMDb trending candidates, filtered against recent Jellyfin activity when configured.
    2. Jellyfin resume queue fallback.
    3. Deterministic static fallback for offline/dev environments.
    """
    warnings: list[str] = []
    recent_titles = _recent_jellyfin_titles()

    trending_title, trending_error = _tmdb_trending_candidate(blocklist=recent_titles)
    if trending_title:
        return trending_title, warnings
    if trending_error:
        warnings.append(trending_error)

    if recent_titles:
        return recent_titles[0], warnings

    warnings.append("Suggestion fallback used because provider data was unavailable.")
    return "The Red Shoes (1948)", warnings


def _tmdb_trending_candidate(blocklist: list[str]) -> tuple[str | None, str | None]:
    api_key = os.getenv("TMDB_API_KEY", "").strip()
    if not api_key:
        return None, "TMDB_API_KEY is not configured; trending suggestion unavailable."

    url = "https://api.themoviedb.org/3/trending/movie/week?" + urlencode({"api_key": api_key})
    payload, error = _http_get_json(url)
    if error:
        return None, f"TMDb trending suggestion failed: {error}."

    results = (payload or {}).get("results", [])
    blocked = {title.lower() for title in blocklist}

    ranked = sorted(
        [movie for movie in results if isinstance(movie, dict)],
        key=lambda movie: (int(movie.get("vote_count") or 0), float(movie.get("popularity") or 0.0)),
        reverse=True,
    )
    for movie in ranked:
        title = str(movie.get("title") or "").strip()
        if not title:
            continue
        if title.lower() in blocked:
            continue
        year = _year_from_release_date(str(movie.get("release_date") or ""))
        if year:
            return f"{title} ({year})", None
        return title, None

    return None, "TMDb trending had no eligible suggestion candidates."


def _recent_jellyfin_titles() -> list[str]:
    base_url = os.getenv("JELLYFIN_URL", "").strip().rstrip("/")
    api_key = os.getenv("JELLYFIN_API_KEY", "").strip()
    user_id = os.getenv("JELLYFIN_USER_ID", "").strip()

    if not base_url or not api_key or not user_id:
        return []

    url = (
        f"{base_url}/Users/{quote(user_id)}/Items/Resume?"
        + urlencode({"Limit": "12", "IncludeItemTypes": "Movie"})
    )
    payload, error = _http_get_json(url, headers={"X-Emby-Token": api_key})
    if error:
        return []

    titles: list[str] = []
    for item in (payload or {}).get("Items", []):
        title = str(item.get("Name") or "").strip()
        if title:
            titles.append(title)
    return titles


def _year_from_release_date(value: str) -> int | None:
    if len(value) < 4:
        return None
    head = value[:4]
    if not head.isdigit():
        return None
    return int(head)
