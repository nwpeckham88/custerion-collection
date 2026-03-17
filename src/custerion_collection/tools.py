from __future__ import annotations

import json
import os
import re
import time
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

try:
    from crewai.tools import tool
except ImportError:  # pragma: no cover
    def tool(_name: str):
        def _decorator(fn):
            return fn

        return _decorator


def fetch_history_context(title: str) -> str:
    """Fetch personal watch context from Jellyfin for the requested title."""
    base_url = os.getenv("JELLYFIN_URL", "").strip().rstrip("/")
    api_key = os.getenv("JELLYFIN_API_KEY", "").strip()
    user_id = os.getenv("JELLYFIN_USER_ID", "").strip()

    if not base_url or not api_key or not user_id:
        return (
            f"Jellyfin adapter is not configured for '{title}'. "
            "Set JELLYFIN_URL, JELLYFIN_API_KEY, and JELLYFIN_USER_ID."
        )

    params = urlencode(
        {
            "Recursive": "true",
            "IncludeItemTypes": "Movie",
            "SearchTerm": title,
            "Limit": "1",
            "SortBy": "SortName",
        }
    )
    headers = {"X-Emby-Token": api_key}
    items_url = f"{base_url}/Users/{quote(user_id)}/Items?{params}"
    items_payload, items_error = _http_get_json(items_url, headers=headers)

    if items_error:
        return f"Jellyfin history lookup failed for '{title}': {items_error}."

    items = (items_payload or {}).get("Items", [])
    if not items:
        return f"No Jellyfin watch-history match found for '{title}'."

    item = items[0]
    user_data = item.get("UserData", {})
    matched_name = item.get("Name", title)
    production_year = item.get("ProductionYear")
    play_count = user_data.get("PlayCount", 0)
    is_favorite = user_data.get("IsFavorite", False)
    last_played = user_data.get("LastPlayedDate", "unknown")

    resume_url = (
        f"{base_url}/Users/{quote(user_id)}/Items/Resume?"
        + urlencode({"Limit": "10", "IncludeItemTypes": "Movie"})
    )
    resume_payload, resume_error = _http_get_json(resume_url, headers=headers)

    recent_titles = []
    if not resume_error and resume_payload:
        recent_titles = [entry.get("Name", "") for entry in resume_payload.get("Items", [])]
        recent_titles = [name for name in recent_titles if name]

    lines = [
        f"Jellyfin match for '{title}': {matched_name} ({production_year or 'year unknown'}).",
        f"Play count: {play_count}; favorite: {'yes' if is_favorite else 'no'}; last played: {last_played}.",
    ]

    if recent_titles:
        lines.append("Recent in-progress films: " + ", ".join(recent_titles[:5]) + ".")
    elif resume_error:
        lines.append(f"Recent activity unavailable: {resume_error}.")

    return "\n".join(lines)


def fetch_cultural_context(title: str) -> str:
    """Fetch historical and critical context from approved cultural providers."""
    search_url = (
        "https://en.wikipedia.org/w/api.php?"
        + urlencode(
            {
                "action": "query",
                "list": "search",
                "srsearch": f"{title} film",
                "format": "json",
                "srlimit": "1",
            }
        )
    )
    search_payload, search_error = _http_get_json(search_url)
    if search_error:
        return f"Wikipedia cultural lookup failed for '{title}': {search_error}."

    search_hits = ((search_payload or {}).get("query") or {}).get("search", [])
    if not search_hits:
        return f"No cultural source match found on Wikipedia for '{title}'."

    top_hit = search_hits[0]
    wiki_title = top_hit.get("title", title)
    snippet = _strip_html(top_hit.get("snippet", ""))

    summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(wiki_title)}"
    summary_payload, summary_error = _http_get_json(summary_url)

    lines = [
        f"Wikipedia match for '{title}': {wiki_title}.",
    ]

    if snippet:
        lines.append(f"Critical-context snippet: {snippet}.")

    if summary_error:
        lines.append(f"Summary unavailable: {summary_error}.")
        return "\n".join(lines)

    extract = (summary_payload or {}).get("extract")
    page_url = ((summary_payload or {}).get("content_urls") or {}).get("desktop", {}).get("page")
    if extract:
        lines.append(f"Summary: {extract}")
    if page_url:
        lines.append(f"Source: {page_url}")

    return "\n".join(lines)


def fetch_technical_context(title: str) -> str:
    """Fetch production and craft signals from TMDb."""
    movie, error = _tmdb_resolve_movie(title)
    if error:
        return f"TMDb technical lookup failed for '{title}': {error}."

    details, details_error = _tmdb_movie_details(movie_id=movie["id"], append="credits")
    if details_error:
        return f"TMDb technical details failed for '{title}': {details_error}."

    credits = details.get("credits", {})
    crew = credits.get("crew", [])
    cast = credits.get("cast", [])

    director = next((entry.get("name") for entry in crew if entry.get("job") == "Director"), None)
    top_cast = ", ".join(actor.get("name", "") for actor in cast[:5] if actor.get("name"))
    runtime = details.get("runtime")
    genres = ", ".join(genre.get("name", "") for genre in details.get("genres", []) if genre.get("name"))

    lines = [
        (
            f"TMDb technical profile for '{title}': {details.get('title', title)} "
            f"({details.get('release_date', 'date unknown')})."
        ),
        f"Director: {director or 'unknown'}.",
    ]

    if runtime:
        lines.append(f"Runtime: {runtime} minutes.")
    if genres:
        lines.append(f"Genres: {genres}.")
    if top_cast:
        lines.append(f"Top billed cast: {top_cast}.")

    return "\n".join(lines)


def fetch_industry_context(title: str) -> str:
    """Fetch production economics and market indicators from TMDb."""
    movie, error = _tmdb_resolve_movie(title)
    if error:
        return f"TMDb industry lookup failed for '{title}': {error}."

    details, details_error = _tmdb_movie_details(movie_id=movie["id"], append="release_dates")
    if details_error:
        return f"TMDb industry details failed for '{title}': {details_error}."

    budget = details.get("budget") or 0
    revenue = details.get("revenue") or 0
    vote_count = details.get("vote_count") or 0
    vote_average = details.get("vote_average") or 0
    release_date = details.get("release_date", "unknown")

    lines = [
        (
            f"TMDb industry profile for '{title}': release date {release_date}, "
            f"rating {vote_average}/10 from {vote_count} votes."
        ),
        f"Budget: ${budget:,}. Revenue: ${revenue:,}.",
    ]

    if budget > 0 and revenue > 0:
        roi = revenue / budget
        lines.append(f"Revenue-to-budget ratio: {roi:.2f}x.")

    return "\n".join(lines)


def fetch_follow_up_media(title: str) -> str:
    """Fetch bounded follow-up links from approved providers."""
    links: list[tuple[str, str]] = []

    wiki_search_url = (
        "https://en.wikipedia.org/w/api.php?"
        + urlencode(
            {
                "action": "query",
                "list": "search",
                "srsearch": f"{title} film",
                "format": "json",
                "srlimit": "1",
            }
        )
    )
    wiki_payload, wiki_error = _http_get_json(wiki_search_url)
    if not wiki_error:
        hits = ((wiki_payload or {}).get("query") or {}).get("search", [])
        if hits:
            article_title = hits[0].get("title", title)
            links.append((f"Wikipedia article: {article_title}", f"https://en.wikipedia.org/wiki/{quote(article_title.replace(' ', '_'))}"))

    movie, tmdb_error = _tmdb_resolve_movie(title)
    if not tmdb_error:
        recs, recs_error = _tmdb_movie_details(movie_id=movie["id"], append="recommendations")
        if not recs_error:
            recommendations = ((recs.get("recommendations") or {}).get("results") or [])
            for rec in recommendations[:3]:
                rec_title = rec.get("title")
                rec_id = rec.get("id")
                if rec_title and rec_id:
                    links.append(
                        (
                            f"Related film: {rec_title}",
                            f"https://www.themoviedb.org/movie/{rec_id}",
                        )
                    )

    youtube_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if youtube_key:
        youtube_url = (
            "https://www.googleapis.com/youtube/v3/search?"
            + urlencode(
                {
                    "part": "snippet",
                    "type": "video",
                    "maxResults": "3",
                    "q": f"{title} film interview essay",
                    "key": youtube_key,
                }
            )
        )
        youtube_payload, youtube_error = _http_get_json(youtube_url)
        if not youtube_error:
            for item in youtube_payload.get("items", []):
                video_id = ((item.get("id") or {}).get("videoId"))
                video_title = ((item.get("snippet") or {}).get("title"))
                if video_id and video_title:
                    links.append((f"YouTube: {video_title}", f"https://www.youtube.com/watch?v={video_id}"))

    deduped: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    for label, url in links:
        if url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append((label, url))

    bounded = deduped[:8]
    if not bounded:
        return (
            f"No approved follow-up media sources available for '{title}'. "
            "Configure TMDB_API_KEY and/or YOUTUBE_API_KEY for richer links."
        )

    lines = [f"Follow-up media for '{title}' (bounded to {len(bounded)} items):"]
    for idx, (label, url) in enumerate(bounded, start=1):
        lines.append(f"{idx}. {label} -> {url}")
    return "\n".join(lines)


def _strip_html(raw: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", raw)
    cleaned = unescape(cleaned)
    return " ".join(cleaned.split())


def _tmdb_resolve_movie(title: str) -> tuple[dict | None, str | None]:
    api_key = os.getenv("TMDB_API_KEY", "").strip()
    if not api_key:
        return None, "TMDB_API_KEY is not configured"

    url = (
        "https://api.themoviedb.org/3/search/movie?"
        + urlencode({"api_key": api_key, "query": title, "include_adult": "false", "page": "1"})
    )
    payload, err = _http_get_json(url)
    if err:
        return None, err

    results = (payload or {}).get("results", [])
    if not results:
        return None, f"no TMDb match found for '{title}'"
    return results[0], None


def _tmdb_movie_details(movie_id: int, append: str | None = None) -> tuple[dict, str | None]:
    api_key = os.getenv("TMDB_API_KEY", "").strip()
    if not api_key:
        return {}, "TMDB_API_KEY is not configured"

    params = {"api_key": api_key}
    if append:
        params["append_to_response"] = append

    url = f"https://api.themoviedb.org/3/movie/{movie_id}?" + urlencode(params)
    payload, err = _http_get_json(url)
    if err:
        return {}, err
    return payload or {}, None


def _http_get_json(url: str, headers: dict[str, str] | None = None) -> tuple[dict | None, str | None]:
    retries = _env_int("HTTP_RETRY_COUNT", default=2, minimum=0)
    backoff = _env_float("HTTP_RETRY_BACKOFF_SECONDS", default=0.4, minimum=0.0)

    last_error: str | None = None
    for attempt in range(retries + 1):
        request = Request(url=url, headers=headers or {}, method="GET")
        try:
            with urlopen(request, timeout=12) as response:
                body = response.read().decode("utf-8")
                return json.loads(body), None
        except HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code not in (429, 500, 502, 503, 504):
                break
        except URLError as exc:
            last_error = f"network error: {exc.reason}"
        except TimeoutError:
            last_error = "request timeout"
        except json.JSONDecodeError:
            return None, "invalid JSON response"

        if attempt < retries:
            time.sleep(backoff * (2**attempt))

    return None, last_error or "request failed"


def _env_int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None:
        value = default
    else:
        try:
            value = int(raw.strip())
        except ValueError:
            value = default

    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _env_float(name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None:
        value = default
    else:
        try:
            value = float(raw.strip())
        except ValueError:
            value = default

    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


@tool("fetch_history_context")
def history_context_tool(title: str) -> str:
    """Fetch user history and preference context for a film title."""
    return fetch_history_context(title)


@tool("fetch_cultural_context")
def cultural_context_tool(title: str) -> str:
    """Fetch historical and critical context for a film title."""
    return fetch_cultural_context(title)


@tool("fetch_technical_context")
def technical_context_tool(title: str) -> str:
    """Fetch technical craft context for a film title."""
    return fetch_technical_context(title)


@tool("fetch_industry_context")
def industry_context_tool(title: str) -> str:
    """Fetch industry and market context for a film title."""
    return fetch_industry_context(title)


@tool("fetch_follow_up_media")
def follow_up_media_tool(title: str) -> str:
    """Fetch bounded follow-up media links for a film title."""
    return fetch_follow_up_media(title)


def curator_tools() -> list:
    return [history_context_tool]


def historian_tools() -> list:
    return [cultural_context_tool]


def technical_tools() -> list:
    return [technical_context_tool]


def industry_tools() -> list:
    return [industry_context_tool]


def follow_up_tools() -> list:
    return [follow_up_media_tool]


def trivia_tools() -> list:
    return [cultural_context_tool, technical_context_tool]
