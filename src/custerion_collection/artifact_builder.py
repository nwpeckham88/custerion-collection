from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from custerion_collection.config import (
    model_name,
    openrouter_extra_headers,
    openrouter_provider_preferences,
)
from custerion_collection.models import (
    CommentarySegment,
    DeepDiveArtifact,
    DeepDiveSection,
    FilmIdentity,
    FollowUpMediaItem,
    SourceCitation,
)


_SECTION_KEYWORDS = {
    "history": ["history", "context", "cultural"],
    "craft": ["craft", "technical", "technique", "cinematography", "editing", "sound"],
    "industry": ["industry", "market", "production", "release", "economics"],
    "lore": ["lore", "trivia", "behind"],
}

_PLACEHOLDER_SOURCE_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "localhost",
}

_TIMESTAMP_RE = re.compile(r"\[(?P<h>\d{1,2}):(?P<m>\d{2})(?::(?P<s>\d{2}))?\]")

_SECTION_FAILURE_MARKERS = (
    "limited confirmed detail",
    "insufficient evidence",
    "no reliable",
    "lookup failed",
    "unavailable",
    "not configured",
    "no cultural source match",
    "no tmdb match",
    "no jellyfin watch-history match",
)


def build_deep_dive_artifact(
    title: str,
    markdown: str,
    film_identity: FilmIdentity | None = None,
) -> DeepDiveArtifact:
    heading_map = _extract_heading_sections(markdown)
    identity = film_identity or _infer_film_identity(title)

    intro = _extract_intro(heading_map, markdown)
    sections = _build_core_sections(heading_map, markdown, identity.title)
    commentary_segments, commentary_mode = _extract_commentary_segments(heading_map, markdown)
    watch_next = _extract_watch_next(heading_map)
    known_unknowns = _extract_known_unknowns(heading_map)
    follow_up_media = _extract_follow_up_media(heading_map)
    citations = _extract_citations(markdown, follow_up_media)

    return DeepDiveArtifact(
        film=identity,
        personalized_intro=intro,
        sections=sections,
        commentary_segments=commentary_segments,
        commentary_mode=commentary_mode,
        watch_next=watch_next,
        known_unknowns=known_unknowns,
        follow_up_media=follow_up_media,
        citations=citations,
        created_at=datetime.now(timezone.utc),
    )


def _infer_film_identity(title: str) -> FilmIdentity:
    match = re.match(r"^(?P<name>.+?)\s*\((?P<year>\d{4})\)$", title.strip())
    if match:
        clean_title = match.group("name").strip()
        year = int(match.group("year"))
    else:
        clean_title = title.strip()
        year = datetime.now(timezone.utc).year

    slug = _slugify(clean_title)
    return FilmIdentity(
        title=clean_title,
        year=year,
        canonical_id=f"local:{slug}:{year}",
    )


def _extract_heading_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_heading = "preamble"
    buffer: list[str] = []

    for line in markdown.splitlines():
        if re.match(r"^#{2,3}\s+", line):
            sections[current_heading] = "\n".join(buffer).strip()
            current_heading = re.sub(r"^#{2,3}\s+", "", line).strip().lower()
            buffer = []
            continue
        buffer.append(line)

    sections[current_heading] = "\n".join(buffer).strip()
    return sections


def _extract_intro(heading_map: dict[str, str], markdown: str) -> str:
    for heading, content in heading_map.items():
        if "intro" in heading or "why this film" in heading or "personal" in heading:
            text = content.strip()
            if text:
                return text

    paragraphs = [part.strip() for part in markdown.split("\n\n") if part.strip()]
    if paragraphs:
        return paragraphs[0]
    return "Personalized framing unavailable from generation output."


def _build_core_sections(heading_map: dict[str, str], markdown: str, film_title: str) -> list[DeepDiveSection]:
    # Keep section order stable for predictable rendering.
    ordered = [
        ("History", _find_section_text(heading_map, _SECTION_KEYWORDS["history"])),
        ("Craft", _find_section_text(heading_map, _SECTION_KEYWORDS["craft"])),
        ("Industry", _find_section_text(heading_map, _SECTION_KEYWORDS["industry"])),
        ("Notable Lore", _find_section_text(heading_map, _SECTION_KEYWORDS["lore"])),
    ]

    missing_sections = [
        name
        for name, content in ordered
        if _section_needs_llm_fallback(content)
    ]
    llm_fallbacks = _llm_section_fallbacks(
        missing_sections=missing_sections,
        film_title=film_title,
        markdown_context=markdown,
    )

    sections: list[DeepDiveSection] = []
    for name, content in ordered:
        text = content.strip() if content else ""
        if _section_needs_llm_fallback(text) and name in llm_fallbacks:
            text = llm_fallbacks[name]
            confidence = 0.45
        else:
            confidence = 0.8 if text else 0.35
        sections.append(
            DeepDiveSection(
                name=name,
                content=text or f"This section has limited confirmed detail in the current source set.",
                confidence=confidence,
            )
        )

    if not any(section.content for section in sections):
        sections.append(
            DeepDiveSection(
                name="Guided Tour",
                content=markdown.strip() or "No content generated.",
                confidence=0.4,
            )
        )

    return sections


def _llm_section_fallbacks(
    *,
    missing_sections: list[str],
    film_title: str,
    markdown_context: str,
) -> dict[str, str]:
    if not missing_sections:
        return {}

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not (openai_key or openrouter_key):
        return {}

    try:
        from litellm import completion  # type: ignore
    except Exception:
        return {}

    model = model_name(role="Trivia Researcher")
    prompt = {
        "film_title": film_title,
        "missing_sections": missing_sections,
        "context_excerpt": markdown_context[:9000],
        "requirements": [
            "Return JSON object mapping section names to concise markdown paragraphs.",
            "Do not include citations or URLs.",
            "If uncertain, explicitly say details may be approximate.",
        ],
    }

    completion_kwargs: dict[str, object] = {}
    headers = openrouter_extra_headers()
    provider_preferences = openrouter_provider_preferences()
    if headers:
        completion_kwargs["extra_headers"] = headers
    if provider_preferences:
        completion_kwargs["provider"] = provider_preferences

    try:
        response = completion(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a fallback film explainer filling missing report sections. "
                        "Return only JSON object with requested section keys."
                    ),
                },
                {"role": "user", "content": str(prompt)},
            ],
            temperature=0.6,
            **completion_kwargs,
        )
    except Exception:
        return {}

    content = ""
    if isinstance(response, dict):
        content = str(response.get("choices", [{}])[0].get("message", {}).get("content", "") or "")
    else:
        choices = getattr(response, "choices", [])
        if choices:
            message = getattr(choices[0], "message", None)
            if message is not None:
                content = getattr(message, "content", "") or ""

    parsed = _parse_json_object(content)
    if not isinstance(parsed, dict):
        return {}

    disclaimer = (
        "LLM-only fallback: this section is entirely generated by the Trivia LLM provider, "
        "without verified search sources, and details may be hallucinated."
    )
    result: dict[str, str] = {}
    for section_name in missing_sections:
        raw = parsed.get(section_name)
        if not isinstance(raw, str):
            continue
        cleaned = raw.strip()
        if not cleaned:
            continue
        result[section_name] = f"{disclaimer}\n\n{cleaned}"
    return result


def _section_needs_llm_fallback(content: str | None) -> bool:
    text = (content or "").strip()
    if not text:
        return True

    lowered = text.lower()
    return any(marker in lowered for marker in _SECTION_FAILURE_MARKERS)


def _parse_json_object(content: str) -> dict[str, object] | None:
    text = content.strip()
    if not text:
        return None

    try:
        import json

        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        import json

        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None

    return None


def _find_section_text(heading_map: dict[str, str], keywords: list[str]) -> str:
    for heading, content in heading_map.items():
        if any(keyword in heading for keyword in keywords):
            return content
    return ""


def _extract_watch_next(heading_map: dict[str, str]) -> list[str]:
    candidates: list[str] = []
    for heading, content in heading_map.items():
        if "watch next" not in heading and "what to watch next" not in heading and "recommend" not in heading:
            continue
        for line in content.splitlines():
            clean = re.sub(r"^\s*[-*\d.]+\s*", "", line).strip()
            if clean:
                candidates.append(clean)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped[:8]


def _extract_commentary_segments(
    heading_map: dict[str, str],
    markdown: str,
) -> tuple[list[CommentarySegment], str]:
    commentary_source = ""
    for heading, content in heading_map.items():
        lowered = heading.lower()
        if "guided commentary" in lowered or "commentary timeline" in lowered or "scene commentary" in lowered:
            commentary_source = content
            break

    if not commentary_source:
        # Fall back to scanning whole markdown for timestamped lines.
        commentary_source = markdown

    raw_segments: list[tuple[int | None, str, str]] = []
    for raw_line in commentary_source.splitlines():
        line = re.sub(r"^\s*[-*\d.]+\s*", "", raw_line).strip()
        if not line:
            continue

        ts_match = _TIMESTAMP_RE.search(line)
        if ts_match:
            timestamp_ms = _timestamp_match_to_ms(ts_match)
            body = line[ts_match.end() :].strip(" -:\t")
            scene_label, commentary = _split_scene_and_commentary(body)
            if commentary:
                raw_segments.append((timestamp_ms, scene_label, commentary))
            continue

        if commentary_source != markdown:
            scene_label, commentary = _split_scene_and_commentary(line)
            if commentary:
                raw_segments.append((None, scene_label, commentary))

    if not raw_segments:
        return [], "none"

    has_timed = any(item[0] is not None for item in raw_segments)
    has_untimed = any(item[0] is None for item in raw_segments)

    if has_timed:
        timed = [item for item in raw_segments if item[0] is not None]
        untimed = [item for item in raw_segments if item[0] is None]
        timed.sort(key=lambda item: int(item[0] or 0))
        raw_segments = timed + untimed

    segments: list[CommentarySegment] = []
    for idx, (timestamp_ms, scene_label, commentary) in enumerate(raw_segments):
        segments.append(
            CommentarySegment(
                order_index=idx,
                timestamp_ms=timestamp_ms,
                scene_label=scene_label,
                commentary=commentary,
                source="timeline_parse",
                confidence=0.7 if timestamp_ms is not None else 0.55,
            )
        )

    mode = "mixed"
    if has_timed and not has_untimed:
        mode = "timed"
    elif has_untimed and not has_timed:
        mode = "untimed"

    return segments[:240], mode


def _timestamp_match_to_ms(match: re.Match[str]) -> int:
    hours_or_minutes = int(match.group("h"))
    minutes_or_seconds = int(match.group("m"))
    seconds = match.group("s")
    if seconds is None:
        total_seconds = hours_or_minutes * 60 + minutes_or_seconds
    else:
        total_seconds = (hours_or_minutes * 3600) + (minutes_or_seconds * 60) + int(seconds)
    return total_seconds * 1000


def _split_scene_and_commentary(text: str) -> tuple[str, str]:
    if not text:
        return "Scene", ""

    for divider in ("::", " - ", " | "):
        if divider in text:
            left, right = text.split(divider, 1)
            scene = left.strip() or "Scene"
            commentary = right.strip()
            return scene, commentary

    return "Scene", text.strip()


def _extract_known_unknowns(heading_map: dict[str, str]) -> list[str]:
    unknowns: list[str] = []

    for heading, content in heading_map.items():
        if "known unknown" in heading:
            for line in content.splitlines():
                clean = re.sub(r"^\s*[-*\d.]+\s*", "", line).strip()
                if clean:
                    unknowns.append(clean)

    if unknowns:
        return unknowns

    fallback_lines = []
    for content in heading_map.values():
        for line in content.splitlines():
            lower = line.lower()
            if "uncertain" in lower or "insufficient evidence" in lower:
                fallback_lines.append(line.strip())

    return fallback_lines[:5]


def _extract_follow_up_media(heading_map: dict[str, str]) -> list[FollowUpMediaItem]:
    lines: list[str] = []
    for heading, content in heading_map.items():
        if "follow-up" in heading or "follow up" in heading or "explore next" in heading or "appendix" in heading:
            lines.extend(content.splitlines())

    items: list[FollowUpMediaItem] = []
    per_kind: dict[str, int] = {"video": 0, "article": 0, "related_film": 0}
    seen_urls: set[str] = set()

    for raw in lines:
        url = _extract_url(raw)
        if not url or url in seen_urls:
            continue
        if _is_placeholder_source_url(url):
            continue
        kind = _classify_media_kind(url)
        if per_kind[kind] >= 3:
            continue

        per_kind[kind] += 1
        seen_urls.add(url)
        title = _line_title(raw, url)
        items.append(
            FollowUpMediaItem(
                kind=kind,
                title=title,
                url=url,
                rationale="Relevant to deepen context from this deep-dive.",
                relevance_score=0.7,
                source_confidence=0.7,
            )
        )

        if len(items) >= 8:
            break

    return items


def _extract_citations(markdown: str, follow_up_media: list[FollowUpMediaItem]) -> list[SourceCitation]:
    urls = re.findall(r"https?://[^\s)]+", markdown)
    urls.extend(str(item.url) for item in follow_up_media if item.url is not None)

    citations: list[SourceCitation] = []
    seen: set[str] = set()
    for idx, url in enumerate(urls, start=1):
        clean = url.rstrip(".,")
        if clean in seen:
            continue
        if _is_placeholder_source_url(clean):
            continue
        seen.add(clean)
        parsed = urlparse(clean)
        provider = parsed.netloc or "unknown"
        source_id = parsed.path.strip("/") or f"source-{idx}"
        claim_ref = _claim_ref_for_url(markdown=markdown, url=clean, fallback_idx=idx)
        citations.append(
            SourceCitation(
                provider=provider,
                source_id=source_id,
                url=clean,
                confidence=0.7,
                claim_ref=claim_ref,
            )
        )

    return citations


def _extract_url(line: str) -> str | None:
    match = re.search(r"https?://[^\s)]+", line)
    if not match:
        return None
    return match.group(0).rstrip(".,")


def _classify_media_kind(url: str) -> str:
    lower = url.lower()
    if "youtube.com" in lower or "youtu.be" in lower:
        return "video"
    if "themoviedb.org/movie" in lower:
        return "related_film"
    return "article"


def _line_title(line: str, url: str) -> str:
    stripped = line.replace(url, "")
    stripped = re.sub(r"^\s*[-*\d.]+\s*", "", stripped).strip(" :\t")
    return stripped or url


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"


def _claim_ref_for_url(markdown: str, url: str, fallback_idx: int) -> str:
    for raw_line in markdown.splitlines():
        if url not in raw_line:
            continue
        candidate = raw_line.replace(url, "")
        candidate = re.sub(r"^\s*[-*\d.]+\s*", "", candidate).strip(" -:\t")
        if not candidate:
            break
        candidate = re.sub(r"\s+", " ", candidate)
        if len(candidate) > 120:
            candidate = candidate[:117].rstrip() + "..."
        return candidate
    return f"claim-{fallback_idx}"


def _is_placeholder_source_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host in _PLACEHOLDER_SOURCE_DOMAINS
