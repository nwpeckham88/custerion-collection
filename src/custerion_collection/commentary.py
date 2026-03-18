from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from custerion_collection.config import (
    commentary_planner_model_name,
    commentary_planning_goal,
    openrouter_extra_headers,
    openrouter_provider_preferences,
)
from custerion_collection.models import DeepDiveArtifact
from custerion_collection.models import CommentarySegment

_SRT_BLOCK_SPLIT_RE = re.compile(r"\n\s*\n", re.MULTILINE)
_SRT_TIMECODE_RE = re.compile(
    r"^(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2},\d{3})"
)


@dataclass(slots=True)
class SubtitleCue:
    start_ms: int
    end_ms: int
    text: str


_STOPWORDS = {
    "the",
    "and",
    "with",
    "that",
    "from",
    "this",
    "into",
    "about",
    "after",
    "before",
    "during",
    "scene",
    "film",
    "movie",
    "character",
    "actors",
    "actor",
}


def parse_srt_cues(srt_text: str) -> list[SubtitleCue]:
    normalized = srt_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    blocks = _SRT_BLOCK_SPLIT_RE.split(normalized)
    cues: list[SubtitleCue] = []

    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if len(lines) < 2:
            continue

        # Support both standard and index-less SRT blocks.
        tc_line = lines[1] if lines[0].isdigit() else lines[0]
        tc_match = _SRT_TIMECODE_RE.match(tc_line)
        if tc_match is None:
            continue

        start_ms = _srt_timestamp_to_ms(tc_match.group("start"))
        end_ms = _srt_timestamp_to_ms(tc_match.group("end"))

        text_lines = lines[2:] if lines[0].isdigit() else lines[1:]
        raw_text = " ".join(text_lines)
        clean_text = _clean_subtitle_text(raw_text)
        if not clean_text:
            continue

        cues.append(SubtitleCue(start_ms=start_ms, end_ms=end_ms, text=clean_text))

    return cues


def cues_to_commentary_segments(cues: list[SubtitleCue], max_segments: int = 240) -> list[CommentarySegment]:
    segments: list[CommentarySegment] = []
    for idx, cue in enumerate(cues[: max(1, max_segments)]):
        scene_label = _scene_label_for_index(idx)
        segments.append(
            CommentarySegment(
                order_index=idx,
                timestamp_ms=cue.start_ms,
                scene_label=scene_label,
                commentary=cue.text,
                source="subtitle_srt",
                confidence=0.6,
            )
        )
    return segments


def parse_srt_to_commentary_segments(srt_text: str, max_segments: int = 240) -> list[CommentarySegment]:
    cues = parse_srt_cues(srt_text)
    return cues_to_commentary_segments(cues=cues, max_segments=max_segments)


def build_goal_driven_commentary_plan(
    subtitle_text: str,
    artifact: DeepDiveArtifact,
    *,
    report_markdown: str,
    max_segments: int = 24,
    spoiler_delay_ms: int = 5000,
    min_gap_ms: int = 18000,
) -> list[CommentarySegment]:
    cues = parse_srt_cues(subtitle_text)
    if not cues:
        return []

    capped_max = max(4, min(max_segments, 40))
    target_goal = build_commentary_planner_instruction(artifact=artifact)
    fact_lines = _extract_candidate_fact_lines(artifact=artifact, limit=capped_max + 10)
    if not fact_lines:
        return cues_to_commentary_segments(cues=cues, max_segments=capped_max)

    llm_plan = _plan_with_llm(
        cues=cues,
        fact_lines=fact_lines,
        report_markdown=report_markdown,
        goal=target_goal,
        max_segments=capped_max,
        spoiler_delay_ms=max(0, spoiler_delay_ms),
    )
    if llm_plan:
        return _normalize_planned_segments(
            planned=llm_plan,
            cues=cues,
            min_gap_ms=max(2000, min_gap_ms),
            max_segments=capped_max,
        )

    return _plan_with_heuristics(
        cues=cues,
        fact_lines=fact_lines,
        max_segments=capped_max,
        spoiler_delay_ms=max(0, spoiler_delay_ms),
        min_gap_ms=max(2000, min_gap_ms),
    )


def commentary_plan_payload(
    *,
    segments: list[CommentarySegment],
    goal: str,
    planner: str,
) -> dict[str, object]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "goal": goal,
        "planner": planner,
        "segments": [segment.model_dump() for segment in segments],
    }


def build_commentary_planner_instruction(artifact: DeepDiveArtifact) -> str:
    sections = ", ".join(section.name for section in artifact.sections[:6]) or "general analysis"
    title = artifact.film.title
    year = artifact.film.year

    return (
        f"{commentary_planning_goal()} "
        f"Target film: {title} ({year}). "
        f"Use report sections ({sections}) as the canonical information source. "
        "Schedule commentary beats to subtitle-grounded moments, avoid early reveals, "
        "and maintain a coherent beginning-middle-end listening arc."
    )


def parse_commentary_plan_payload(payload: dict[str, object]) -> list[CommentarySegment]:
    raw = payload.get("segments")
    if not isinstance(raw, list):
        return []

    segments: list[CommentarySegment] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            segments.append(CommentarySegment.model_validate(item))
        except Exception:
            continue

    ordered = sorted(segments, key=lambda seg: (seg.timestamp_ms if seg.timestamp_ms is not None else 10**12, seg.order_index))
    return [
        CommentarySegment(
            order_index=index,
            timestamp_ms=segment.timestamp_ms,
            scene_label=segment.scene_label,
            commentary=segment.commentary,
            source=segment.source,
            confidence=segment.confidence,
        )
        for index, segment in enumerate(ordered)
    ]


def _srt_timestamp_to_ms(value: str) -> int:
    hh_str, mm_str, rest = value.split(":")
    ss_str, ms_str = rest.split(",")
    hh = int(hh_str)
    mm = int(mm_str)
    ss = int(ss_str)
    ms = int(ms_str)
    return ((hh * 3600 + mm * 60 + ss) * 1000) + ms


def _clean_subtitle_text(value: str) -> str:
    # Remove inline formatting tags often present in downloaded subtitle files.
    no_tags = re.sub(r"<[^>]+>", "", value)
    collapsed = re.sub(r"\s+", " ", no_tags).strip()
    return collapsed


def _scene_label_for_index(index: int) -> str:
    return f"Subtitle Cue {index + 1:03d}"


def _extract_candidate_fact_lines(artifact: DeepDiveArtifact, limit: int) -> list[str]:
    lines: list[str] = []

    if artifact.personalized_intro.strip():
        lines.extend(_split_sentences(artifact.personalized_intro))

    for section in artifact.sections:
        lines.extend(_split_sentences(section.content))

    lines.extend(item.strip() for item in artifact.known_unknowns if item.strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for line in lines:
        clean = re.sub(r"\s+", " ", line).strip()
        if len(clean) < 30:
            continue
        if clean.lower() in seen:
            continue
        seen.add(clean.lower())
        deduped.append(clean)
        if len(deduped) >= max(4, limit):
            break

    return deduped


def _split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+", text.strip())
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _plan_with_heuristics(
    *,
    cues: list[SubtitleCue],
    fact_lines: list[str],
    max_segments: int,
    spoiler_delay_ms: int,
    min_gap_ms: int,
) -> list[CommentarySegment]:
    plan_candidates: list[tuple[int, str, float]] = []
    matched_indexes: set[int] = set()

    for fact in fact_lines:
        cue_idx = _find_matching_cue_index(cues=cues, fact=fact)
        if cue_idx is None:
            continue
        matched_indexes.add(cue_idx)
        ts = cues[cue_idx].start_ms + spoiler_delay_ms
        plan_candidates.append((ts, fact, 0.74))

    remaining_facts = [fact for fact in fact_lines if fact not in {item[1] for item in plan_candidates}]
    if remaining_facts:
        fallback_times = _distributed_times(cues=cues, count=len(remaining_facts), offset_ms=spoiler_delay_ms)
        for idx, fact in enumerate(remaining_facts):
            plan_candidates.append((fallback_times[idx], fact, 0.6))

    plan_candidates.sort(key=lambda item: item[0])

    scheduled: list[CommentarySegment] = []
    last_ts = -10**12
    for ts, fact, confidence in plan_candidates:
        if ts - last_ts < min_gap_ms:
            ts = last_ts + min_gap_ms

        scheduled.append(
            CommentarySegment(
                order_index=len(scheduled),
                timestamp_ms=max(0, ts),
                scene_label=f"Planned Insight {len(scheduled) + 1:02d}",
                commentary=fact,
                source="subtitle_goal_planner",
                confidence=confidence,
            )
        )
        last_ts = ts
        if len(scheduled) >= max_segments:
            break

    return scheduled


def _find_matching_cue_index(cues: list[SubtitleCue], fact: str) -> int | None:
    keywords = _keywords_for_fact(fact)
    if not keywords:
        return None

    for idx, cue in enumerate(cues):
        lowered = cue.text.lower()
        if any(keyword in lowered for keyword in keywords):
            return idx
    return None


def _keywords_for_fact(fact: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z'\-]{2,}", fact)
    if not words:
        return []

    title_case = [word.lower() for word in words if word[:1].isupper() and word.lower() not in _STOPWORDS]
    meaningful = [word.lower() for word in words if len(word) >= 5 and word.lower() not in _STOPWORDS]

    ranked = title_case + meaningful
    deduped: list[str] = []
    seen: set[str] = set()
    for keyword in ranked:
        if keyword in seen:
            continue
        seen.add(keyword)
        deduped.append(keyword)
        if len(deduped) >= 8:
            break
    return deduped


def _distributed_times(cues: list[SubtitleCue], count: int, offset_ms: int) -> list[int]:
    if count <= 0:
        return []

    first = cues[0].start_ms
    last = cues[-1].start_ms
    duration = max(1, last - first)
    return [
        first + int(duration * ((idx + 1) / (count + 1))) + offset_ms
        for idx in range(count)
    ]


def _plan_with_llm(
    *,
    cues: list[SubtitleCue],
    fact_lines: list[str],
    report_markdown: str,
    goal: str,
    max_segments: int,
    spoiler_delay_ms: int,
) -> list[dict[str, object]]:
    model = commentary_planner_model_name()

    try:
        from litellm import completion  # type: ignore
    except Exception:
        return []

    compact_cues = [
        {
            "start_ms": cue.start_ms,
            "text": cue.text[:120],
        }
        for cue in cues[:: max(1, len(cues) // 120)]
    ]

    prompt_payload = {
        "goal": goal,
        "max_segments": max_segments,
        "spoiler_delay_ms": spoiler_delay_ms,
        "facts": fact_lines[: max_segments + 8],
        "subtitle_cues": compact_cues,
        "report_markdown": report_markdown[:12000],
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
                        "You schedule spoiler-aware movie audio commentary. "
                        "Return only JSON: an array of objects with keys "
                        "timestamp_ms, scene_label, commentary, confidence."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt_payload),
                },
            ],
            temperature=0.2,
            **completion_kwargs,
        )
    except Exception:
        return []

    content = ""
    if isinstance(response, dict):
        content = str(response.get("choices", [{}])[0].get("message", {}).get("content", "") or "")
    else:
        choices = getattr(response, "choices", [])
        if choices:
            message = getattr(choices[0], "message", None)
            if message is not None:
                content = getattr(message, "content", "") or ""

    raw = _parse_json_array(content)
    if not isinstance(raw, list):
        return []

    normalized: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        ts = item.get("timestamp_ms")
        scene_label = str(item.get("scene_label") or "Planned Insight")
        commentary = str(item.get("commentary") or "").strip()
        confidence = float(item.get("confidence") or 0.65)
        if not isinstance(ts, int) or ts < 0 or not commentary:
            continue
        normalized.append(
            {
                "timestamp_ms": ts,
                "scene_label": scene_label,
                "commentary": commentary,
                "confidence": max(0.0, min(confidence, 1.0)),
            }
        )
        if len(normalized) >= max_segments:
            break

    return normalized


def _parse_json_array(content: str) -> object:
    text = content.strip()
    if not text:
        return None

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except Exception:
        return None


def _normalize_planned_segments(
    *,
    planned: list[dict[str, object]],
    cues: list[SubtitleCue],
    min_gap_ms: int,
    max_segments: int,
) -> list[CommentarySegment]:
    if not planned:
        return []

    movie_end_ms = cues[-1].end_ms if cues else 0
    entries = sorted(planned, key=lambda item: int(item.get("timestamp_ms") or 0))
    segments: list[CommentarySegment] = []
    last_ts = -10**12
    for item in entries:
        ts = int(item.get("timestamp_ms") or 0)
        if ts <= last_ts:
            ts = last_ts + min_gap_ms
        if movie_end_ms > 0:
            ts = min(ts, max(0, movie_end_ms - 1000))

        commentary = str(item.get("commentary") or "").strip()
        if not commentary:
            continue

        segments.append(
            CommentarySegment(
                order_index=len(segments),
                timestamp_ms=ts,
                scene_label=str(item.get("scene_label") or f"Planned Insight {len(segments) + 1:02d}"),
                commentary=commentary,
                source="subtitle_goal_planner",
                confidence=max(0.0, min(float(item.get("confidence") or 0.7), 1.0)),
            )
        )
        last_ts = ts
        if len(segments) >= max_segments:
            break
    return segments
