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
        fallback = _openrouter_grounded_research(
            title=title,
            section="Cultural History",
            failure_reason=search_error,
        )
        if fallback:
            return fallback
        return f"Wikipedia cultural lookup failed for '{title}': {search_error}."

    search_hits = ((search_payload or {}).get("query") or {}).get("search", [])
    if not search_hits:
        fallback = _openrouter_grounded_research(
            title=title,
            section="Cultural History",
            failure_reason="No cultural source match found on Wikipedia",
        )
        if fallback:
            return fallback
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
        fallback = _openrouter_grounded_research(
            title=title,
            section="Technical Craft",
            failure_reason=error,
        )
        if fallback:
            return fallback
        return f"TMDb technical lookup failed for '{title}': {error}."

    details, details_error = _tmdb_movie_details(movie_id=movie["id"], append="credits")
    if details_error:
        fallback = _openrouter_grounded_research(
            title=title,
            section="Technical Craft",
            failure_reason=details_error,
        )
        if fallback:
            return fallback
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
        fallback = _openrouter_grounded_research(
            title=title,
            section="Industry",
            failure_reason=error,
        )
        if fallback:
            return fallback
        return f"TMDb industry lookup failed for '{title}': {error}."

    details, details_error = _tmdb_movie_details(movie_id=movie["id"], append="release_dates")
    if details_error:
        fallback = _openrouter_grounded_research(
            title=title,
            section="Industry",
            failure_reason=details_error,
        )
        if fallback:
            return fallback
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


def fetch_wikipedia_special_effects_research(title: str) -> str:
    """Run 3-level (seed + two follow-ups) Wikipedia research focused on effects/craft."""

    return _wikipedia_multi_hop_research(title=title, focus="special_effects")


def fetch_wikipedia_production_research(title: str) -> str:
    """Run 3-level (seed + two follow-ups) Wikipedia research focused on production history."""

    return _wikipedia_multi_hop_research(title=title, focus="production")


def fetch_wikipedia_actor_research(title: str) -> str:
    """Run 3-level (seed + two follow-ups) Wikipedia research focused on actors/cast."""

    return _wikipedia_multi_hop_research(title=title, focus="actors")


def fetch_wikipedia_trivia_research(title: str) -> str:
    """Run 3-level (seed + two follow-ups) Wikipedia research focused on notable trivia."""

    return _wikipedia_multi_hop_research(title=title, focus="trivia")


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
        fallback = _openrouter_grounded_research(
            title=title,
            section="Follow-up Media",
            failure_reason="No approved follow-up media sources available",
        )
        if fallback:
            return fallback
        return (
            f"No approved follow-up media sources available for '{title}'. "
            "Configure TMDB_API_KEY and/or YOUTUBE_API_KEY for richer links."
        )

    lines = [f"Follow-up media for '{title}' (bounded to {len(bounded)} items):"]
    for idx, (label, url) in enumerate(bounded, start=1):
        lines.append(f"{idx}. {label} -> {url}")
    return "\n".join(lines)


def fetch_scene_transcript_context(title: str) -> str:
    """Fetch transcript-like timestamp hints to support guided commentary timelines."""
    hints: list[str] = []

    movie, tmdb_error = _tmdb_resolve_movie(title)
    if not tmdb_error and movie:
        details, details_error = _tmdb_movie_details(movie_id=movie["id"], append=None)
        if not details_error:
            runtime = details.get("runtime")
            if isinstance(runtime, int) and runtime > 0:
                hints.append(
                    f"Runtime hint: {runtime} minutes. Approximate scene checkpoints can be mapped across 00:00 to {runtime:02d}:00."
                )

    youtube_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if youtube_key:
        youtube_url = (
            "https://www.googleapis.com/youtube/v3/search?"
            + urlencode(
                {
                    "part": "snippet",
                    "type": "video",
                    "maxResults": "5",
                    "q": f"{title} scene breakdown timestamps",
                    "key": youtube_key,
                }
            )
        )
        payload, error = _http_get_json(youtube_url)
        if not error:
            for item in payload.get("items", []):
                snippet = item.get("snippet") or {}
                video_id = (item.get("id") or {}).get("videoId")
                label = snippet.get("title")
                desc = (snippet.get("description") or "").strip()
                if not label or not video_id:
                    continue
                stamp_hits = re.findall(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", desc)
                stamp_preview = ", ".join(stamp_hits[:4]) if stamp_hits else "no explicit timestamps in snippet"
                hints.append(
                    "YouTube transcript lead: "
                    f"{label} (https://www.youtube.com/watch?v={video_id}) | snippet timestamps: {stamp_preview}."
                )

    wiki_search_url = (
        "https://en.wikipedia.org/w/api.php?"
        + urlencode(
            {
                "action": "query",
                "list": "search",
                "srsearch": f"{title} plot",
                "format": "json",
                "srlimit": "1",
            }
        )
    )
    wiki_payload, wiki_error = _http_get_json(wiki_search_url)
    if not wiki_error:
        hits = ((wiki_payload or {}).get("query") or {}).get("search", [])
        if hits:
            snippet = _strip_html(hits[0].get("snippet", ""))
            if snippet:
                hints.append(f"Plot context for scene anchoring: {snippet}.")

    if not hints:
        fallback = _openrouter_grounded_research(
            title=title,
            section="Scene Transcript Context",
            failure_reason="No reliable timestamped transcript context found",
        )
        if fallback:
            return fallback
        return (
            f"No reliable timestamped transcript context found for '{title}'. "
            "Fallback guidance: generate untimed commentary lines with scene labels and keep statements source-grounded."
        )

    return "\n".join(hints)


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


def _http_post_json(
    url: str,
    payload: dict,
    headers: dict[str, str] | None = None,
) -> tuple[dict | None, str | None]:
    retries = _env_int("HTTP_RETRY_COUNT", default=2, minimum=0)
    backoff = _env_float("HTTP_RETRY_BACKOFF_SECONDS", default=0.4, minimum=0.0)

    merged_headers = {
        "content-type": "application/json",
    }
    if headers:
        merged_headers.update(headers)

    body = json.dumps(payload).encode("utf-8")
    last_error: str | None = None
    for attempt in range(retries + 1):
        request = Request(url=url, headers=merged_headers, data=body, method="POST")
        try:
            with urlopen(request, timeout=24) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw), None
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


def _wikipedia_multi_hop_research(
    *,
    title: str,
    focus: str,
    max_levels: int = 3,
    max_results_per_query: int = 3,
) -> str:
    """Perform Wikipedia-first research with two follow-up query rounds.

    Level 1: seed query for the film page.
    Level 2-3: follow-up queries planned from seed article context.
    """

    bounded_levels = max(1, min(max_levels, 3))
    bounded_results = max(1, min(max_results_per_query, 3))

    seed_query = f"{title} film"
    seed_hits, seed_error = _wikipedia_search(seed_query, limit=bounded_results)
    if seed_error:
        return f"Wikipedia research ({focus}) failed at seed query '{seed_query}': {seed_error}."
    if not seed_hits:
        return f"Wikipedia research ({focus}) found no seed results for '{seed_query}'."

    seed = seed_hits[0]
    seed_title = str(seed.get("title") or title)
    summary, summary_url, summary_error = _wikipedia_summary(seed_title)
    section_titles, sections_error = _wikipedia_section_titles(seed_title)

    plan_queries = _derive_follow_up_queries(
        title=title,
        seed_title=seed_title,
        summary=summary,
        section_titles=section_titles,
        focus=focus,
        limit=max(0, bounded_levels - 1),
    )

    lines = [
        f"Wikipedia multi-hop research ({focus}) for '{title}'",
        f"Level 1 seed query: {seed_query}",
        f"Seed article: {seed_title}" + (f" ({summary_url})" if summary_url else ""),
    ]

    if summary_error:
        lines.append(f"Seed summary unavailable: {summary_error}.")
    elif summary:
        lines.append(f"Seed summary: {summary}")

    if sections_error:
        lines.append(f"Seed sections unavailable: {sections_error}.")
    elif section_titles:
        lines.append("Seed sections: " + ", ".join(section_titles[:8]))

    if plan_queries:
        lines.append("Research plan:")
        for idx, query in enumerate(plan_queries, start=2):
            lines.append(f"- Level {idx}: {query}")

    findings: list[str] = []
    for level_index, query in enumerate(plan_queries, start=2):
        hits, query_error = _wikipedia_search(query, limit=bounded_results)
        if query_error:
            findings.append(f"Level {level_index} query failed ('{query}'): {query_error}.")
            continue
        if not hits:
            findings.append(f"Level {level_index} query returned no results ('{query}').")
            continue

        findings.append(f"Level {level_index} findings for '{query}':")
        for rank, hit in enumerate(hits[:bounded_results], start=1):
            hit_title = str(hit.get("title") or "Unknown")
            snippet = _strip_html(str(hit.get("snippet") or ""))
            page_url = f"https://en.wikipedia.org/wiki/{quote(hit_title.replace(' ', '_'))}"
            findings.append(f"  {rank}. {hit_title} - {snippet} ({page_url})")

    if findings:
        lines.append("Findings:")
        lines.extend(findings)

    return "\n".join(lines)


def _wikipedia_search(query: str, limit: int = 3) -> tuple[list[dict], str | None]:
    search_url = (
        "https://en.wikipedia.org/w/api.php?"
        + urlencode(
            {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": str(max(1, min(limit, 10))),
            }
        )
    )
    payload, error = _http_get_json(search_url)
    if error:
        return [], error
    hits = ((payload or {}).get("query") or {}).get("search", [])
    if not isinstance(hits, list):
        return [], "invalid response shape"
    return [hit for hit in hits if isinstance(hit, dict)], None


def _wikipedia_summary(page_title: str) -> tuple[str, str | None, str | None]:
    summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(page_title)}"
    payload, error = _http_get_json(summary_url)
    if error:
        return "", None, error

    extract = str((payload or {}).get("extract") or "").strip()
    page_url = ((payload or {}).get("content_urls") or {}).get("desktop", {}).get("page")
    page_url_value = str(page_url) if page_url else None
    return extract, page_url_value, None


def _wikipedia_section_titles(page_title: str) -> tuple[list[str], str | None]:
    url = (
        "https://en.wikipedia.org/w/api.php?"
        + urlencode(
            {
                "action": "parse",
                "page": page_title,
                "prop": "sections",
                "format": "json",
            }
        )
    )
    payload, error = _http_get_json(url)
    if error:
        return [], error

    raw_sections = ((payload or {}).get("parse") or {}).get("sections", [])
    if not isinstance(raw_sections, list):
        return [], "invalid section response shape"

    titles: list[str] = []
    seen: set[str] = set()
    for section in raw_sections:
        if not isinstance(section, dict):
            continue
        line = str(section.get("line") or "").strip()
        if not line:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        titles.append(line)
        if len(titles) >= 20:
            break

    return titles, None


def _derive_follow_up_queries(
    *,
    title: str,
    seed_title: str,
    summary: str,
    section_titles: list[str],
    focus: str,
    limit: int,
) -> list[str]:
    bounded = max(0, min(limit, 2))
    if bounded == 0:
        return []

    focus_terms = {
        "special_effects": {"effects", "cinematography", "design", "visual", "filming", "sound"},
        "production": {"production", "development", "release", "reception", "box", "office"},
        "actors": {"cast", "performances", "character", "actor", "actors"},
        "trivia": {"legacy", "themes", "references", "impact", "adaptation", "music"},
    }.get(focus, set())

    section_driven_terms: list[str] = []
    for section in section_titles:
        normalized = re.sub(r"\s+", " ", section).strip()
        lower = normalized.lower()
        if lower in {"see also", "references", "external links", "notes"}:
            continue
        if focus_terms and not any(term in lower for term in focus_terms):
            continue
        section_driven_terms.append(normalized)
        if len(section_driven_terms) >= bounded:
            break

    hinted = _extract_wikipedia_hint_terms(summary) if summary else []
    queries: list[str] = []

    for section_topic in section_driven_terms:
        queries.append(f"{seed_title} {section_topic}")
        if len(queries) >= bounded:
            return queries

    if hinted:
        queries.append(f"{seed_title} {' '.join(hinted[:4])}")
    if len(queries) < bounded:
        queries.append(f"{title} film legacy analysis")

    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        key = query.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(query)
        if len(deduped) >= bounded:
            break

    return deduped


def _extract_wikipedia_hint_terms(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z'\-]{3,}", text)
    stop = {
        "with",
        "that",
        "from",
        "this",
        "film",
        "movie",
        "about",
        "after",
        "before",
        "their",
        "which",
        "while",
        "where",
        "during",
    }

    seen: set[str] = set()
    result: list[str] = []
    for word in words:
        key = word.lower()
        if key in stop or key in seen:
            continue
        seen.add(key)
        result.append(key)
        if len(result) >= 8:
            break
    return result


def _openrouter_auth() -> tuple[str, str] | None:
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    key = openrouter_key or openai_key
    if not key:
        return None

    openrouter_base = os.getenv("OPENROUTER_API_BASE", "").strip()
    openai_base = os.getenv("OPENAI_BASE_URL", "").strip()
    if openrouter_base:
        return key, openrouter_base.rstrip("/")
    if openai_base and "openrouter.ai" in openai_base.lower():
        return key, openai_base.rstrip("/")
    if key.startswith("sk-or-v1-"):
        return key, "https://openrouter.ai/api/v1"
    return None


def _openrouter_grounded_research(
    *,
    title: str,
    section: str,
    failure_reason: str,
) -> str | None:
    auth = _openrouter_auth()
    if auth is None:
        return None

    key, base_url = auth
    model = os.getenv("OPENROUTER_GROUNDED_RESEARCH_MODEL", "openrouter/perplexity/sonar").strip()
    if not model:
        model = "openrouter/perplexity/sonar"

    headers = {
        "Authorization": f"Bearer {key}",
    }
    referer = os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
    app_title = os.getenv("OPENROUTER_APP_TITLE", "").strip()
    if referer:
        headers["HTTP-Referer"] = referer
    if app_title:
        headers["X-OpenRouter-Title"] = app_title

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a film research assistant. Provide grounded research with explicit source URLs. "
                    "When uncertain, say so plainly and avoid fabricated certainty."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Section: {section}\n"
                    f"Film: {title}\n"
                    f"Primary provider failed: {failure_reason}\n\n"
                    "Provide concise replacement context and include 2-5 source URLs inline."
                ),
            },
        ],
        "temperature": 0.2,
    }

    response, error = _http_post_json(f"{base_url}/chat/completions", payload=payload, headers=headers)
    if error or not response:
        return None

    content = ""
    choices = response.get("choices") if isinstance(response, dict) else None
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = str(message.get("content") or "").strip()

    if not content:
        return None

    return (
        f"OpenRouter grounded fallback for '{title}' ({section}) after provider failure '{failure_reason}'.\n"
        f"Model: {model}.\n"
        f"{content}"
    )


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


@tool("fetch_scene_transcript_context")
def scene_transcript_context_tool(title: str) -> str:
    """Fetch timestamp and transcript context for guided movie commentary."""
    return fetch_scene_transcript_context(title)


@tool("fetch_wikipedia_special_effects_research")
def wikipedia_special_effects_research_tool(title: str) -> str:
    """Wikipedia-first multi-hop research for special effects and craft details."""

    return fetch_wikipedia_special_effects_research(title)


@tool("fetch_wikipedia_production_research")
def wikipedia_production_research_tool(title: str) -> str:
    """Wikipedia-first multi-hop research for production and development history."""

    return fetch_wikipedia_production_research(title)


@tool("fetch_wikipedia_actor_research")
def wikipedia_actor_research_tool(title: str) -> str:
    """Wikipedia-first multi-hop research for actors and performance context."""

    return fetch_wikipedia_actor_research(title)


@tool("fetch_wikipedia_trivia_research")
def wikipedia_trivia_research_tool(title: str) -> str:
    """Wikipedia-first multi-hop research for high-signal trivia context."""

    return fetch_wikipedia_trivia_research(title)


def curator_tools() -> list:
    return [history_context_tool]


def historian_tools() -> list:
    return [cultural_context_tool, wikipedia_production_research_tool]


def technical_tools() -> list:
    return [technical_context_tool, wikipedia_special_effects_research_tool]


def industry_tools() -> list:
    return [industry_context_tool, wikipedia_production_research_tool]


def follow_up_tools() -> list:
    return [follow_up_media_tool]


def trivia_tools() -> list:
    return [
        wikipedia_trivia_research_tool,
        wikipedia_actor_research_tool,
        cultural_context_tool,
        technical_context_tool,
    ]


def commentary_tools() -> list:
    return [scene_transcript_context_tool, cultural_context_tool, technical_context_tool]
