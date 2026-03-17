from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from custerion_collection.models import (
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


def build_deep_dive_artifact(
    title: str,
    markdown: str,
    film_identity: FilmIdentity | None = None,
) -> DeepDiveArtifact:
    heading_map = _extract_heading_sections(markdown)
    identity = film_identity or _infer_film_identity(title)

    intro = _extract_intro(heading_map, markdown)
    sections = _build_core_sections(heading_map, markdown)
    watch_next = _extract_watch_next(heading_map)
    known_unknowns = _extract_known_unknowns(heading_map)
    follow_up_media = _extract_follow_up_media(heading_map)
    citations = _extract_citations(markdown, follow_up_media)

    return DeepDiveArtifact(
        film=identity,
        personalized_intro=intro,
        sections=sections,
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


def _build_core_sections(heading_map: dict[str, str], markdown: str) -> list[DeepDiveSection]:
    # Keep section order stable for predictable rendering.
    ordered = [
        ("History", _find_section_text(heading_map, _SECTION_KEYWORDS["history"])),
        ("Craft", _find_section_text(heading_map, _SECTION_KEYWORDS["craft"])),
        ("Industry", _find_section_text(heading_map, _SECTION_KEYWORDS["industry"])),
        ("Notable Lore", _find_section_text(heading_map, _SECTION_KEYWORDS["lore"])),
    ]

    sections: list[DeepDiveSection] = []
    for name, content in ordered:
        text = content.strip() if content else ""
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
