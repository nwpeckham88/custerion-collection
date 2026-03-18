from __future__ import annotations

import os
import re
import logging
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

import json

from custerion_collection.commentary import (
    build_commentary_planner_instruction,
    build_goal_driven_commentary_plan,
    commentary_plan_payload,
    parse_commentary_plan_payload,
    parse_srt_to_commentary_segments,
)
from custerion_collection.service import execute_deep_dive, render_html_report_with_retry
from custerion_collection.storage import (
    artifact_title_for_slug,
    latest_commentary_plan_artifact_for_slug,
    list_recent_artifacts,
    latest_subtitle_artifact_for_slug,
    upsert_commentary_plan_artifact_for_slug,
    load_artifact_for_slug,
    latest_html_artifact_for_slug,
    latest_markdown_artifact_for_slug,
    upsert_subtitle_artifact_for_slug,
    upsert_html_artifact_for_slug,
)
from custerion_collection.tts import list_tts_voices_for_slug, synthesize_tts_audio_for_slug, tts_runtime_label


logger = logging.getLogger(__name__)


def _tts_enabled() -> bool:
    raw = os.getenv("ENABLE_TTS", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


class DeepDiveRequest(BaseModel):
    title: str | None = None
    suggest: bool = False
    process_mode: str | None = Field(default=None, pattern="^(hierarchical|sequential)?$")
    dry_run: bool = False


class DeepDiveResponse(BaseModel):
    title: str
    status: str
    warnings: list[str]
    markdown: str
    diagnostics_path: str
    markdown_path: str | None = None
    artifact_json_path: str | None = None
    html_path: str | None = None


class ArtifactSummary(BaseModel):
    title: str
    slug: str
    markdown_path: str | None = None
    artifact_json_path: str | None = None
    html_path: str | None = None
    tts_audio_path: str | None = None
    updated_at: str


class DeepDiveStartResponse(BaseModel):
    run_id: str
    status: str
    stage: str
    progress: int


class DeepDiveRunStatus(BaseModel):
    run_id: str
    status: str
    stage: str
    progress: int
    started_at: str
    updated_at: str
    events: list[str] = Field(default_factory=list)
    result: DeepDiveResponse | None = None
    error: str | None = None


class HtmlRegenerateResponse(BaseModel):
    slug: str
    html_path: str
    warning: str | None = None


class ArtifactTtsVoicesResponse(BaseModel):
    slug: str
    model: str
    default_voice: str
    voices: list[str]


class CommentarySegmentResponse(BaseModel):
    order_index: int
    timestamp_ms: int | None = None
    scene_label: str
    commentary: str
    source: str | None = None
    confidence: float


class ArtifactCommentaryResponse(BaseModel):
    slug: str
    title: str
    commentary_mode: str
    duration_ms: int
    segments: list[CommentarySegmentResponse]
    external_playback: dict[str, str | int | None]


class ArtifactCommentaryRealtimeResponse(BaseModel):
    slug: str
    commentary_mode: str
    position_ms: int
    active_segment: CommentarySegmentResponse | None = None
    upcoming_segments: list[CommentarySegmentResponse] = Field(default_factory=list)


class CommentarySubtitleImportRequest(BaseModel):
    subtitle_text: str = Field(min_length=1)


class CommentarySubtitleImportResponse(BaseModel):
    slug: str
    subtitle_path: str
    commentary_plan_path: str | None = None
    planning_goal: str
    segment_count: int
    commentary_mode: str


_PLACEHOLDER_URL_RE = re.compile(r"https?://(?:www\.)?(example\.com|example\.org|example\.net|localhost)(?:/[^\s\"'<>]*)?", re.IGNORECASE)


def _strip_placeholder_source_links_from_html(html: str) -> str:
    # Prevent placeholder citations from appearing in rendered report pages.
    return _PLACEHOLDER_URL_RE.sub("[placeholder source removed]", html)


def _inject_tts_controls(html: str, slug: str) -> str:
    marker = "data-custerion-tts"
    if marker in html:
        return html

    block = f"""
<div data-custerion-tts style="position:fixed;right:16px;bottom:16px;z-index:9999;background:#111827;color:#f9fafb;padding:10px 12px;border-radius:10px;box-shadow:0 12px 30px rgba(0,0,0,.35);font-family:system-ui,sans-serif;display:flex;gap:8px;align-items:center;flex-wrap:wrap;max-width:92vw;">
    <label style="font-size:12px;opacity:.9;">Voice</label>
    <select id="custerion-tts-voice" style="border-radius:6px;border:1px solid #374151;background:#0b1220;color:#f9fafb;padding:4px 8px;"></select>
    <label style="font-size:12px;opacity:.9;">Read</label>
    <select id="custerion-tts-mode" style="border-radius:6px;border:1px solid #374151;background:#0b1220;color:#f9fafb;padding:4px 8px;">
        <option value="summary">Summary</option>
        <option value="full" selected>Full report</option>
    </select>
    <button id="custerion-tts-play" style="border:0;border-radius:6px;background:#10b981;color:#052e16;padding:6px 10px;font-weight:700;cursor:pointer;">Play</button>
    <button id="custerion-tts-stop" style="border:0;border-radius:6px;background:#ef4444;color:#fff;padding:6px 10px;font-weight:700;cursor:pointer;">Stop</button>
    <audio id="custerion-tts-audio" preload="none"></audio>
</div>
<script>
(function() {{
    var slug = {slug!r};
    var voiceSelect = document.getElementById('custerion-tts-voice');
    var modeSelect = document.getElementById('custerion-tts-mode');
    var playBtn = document.getElementById('custerion-tts-play');
    var stopBtn = document.getElementById('custerion-tts-stop');
    var audio = document.getElementById('custerion-tts-audio');
    if (!voiceSelect || !modeSelect || !playBtn || !stopBtn || !audio) return;

    fetch('/api/artifacts/' + encodeURIComponent(slug) + '/tts/voices')
        .then(function(r) {{ return r.json(); }})
        .then(function(payload) {{
            var voices = Array.isArray(payload.voices) ? payload.voices : [];
            var defaultVoice = payload.default_voice || voices[0] || 'default';
            voices.forEach(function(v) {{
                var opt = document.createElement('option');
                opt.value = v;
                opt.textContent = v;
                if (v === defaultVoice) opt.selected = true;
                voiceSelect.appendChild(opt);
            }});
            if (voiceSelect.options.length === 0) {{
                var opt = document.createElement('option');
                opt.value = 'default';
                opt.textContent = 'default';
                voiceSelect.appendChild(opt);
            }}
        }})
        .catch(function(err) {{
            console.error('TTS voice list failed', err);
        }});

    playBtn.addEventListener('click', function() {{
        var voice = voiceSelect.value || 'default';
        var mode = modeSelect.value || 'full';
        audio.src = '/api/artifacts/' + encodeURIComponent(slug) + '/tts/audio?voice=' + encodeURIComponent(voice) + '&mode=' + encodeURIComponent(mode);
        audio.play().catch(function(err) {{ console.error('TTS playback failed', err); }});
    }});

    stopBtn.addEventListener('click', function() {{
        audio.pause();
        audio.currentTime = 0;
    }});
}})();
</script>
"""

    if "</body>" in html:
        return html.replace("</body>", block + "\n</body>")
    return html + block


def _subtitle_segments_for_slug(slug: str) -> list[CommentarySegmentResponse]:
    commentary_plan_path = latest_commentary_plan_artifact_for_slug(slug)
    if commentary_plan_path is not None and commentary_plan_path.exists():
        try:
            payload = json.loads(commentary_plan_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                planned_segments = parse_commentary_plan_payload(payload)
                if planned_segments:
                    return [CommentarySegmentResponse(**segment.model_dump()) for segment in planned_segments]
        except Exception:
            pass

    subtitle_path = latest_subtitle_artifact_for_slug(slug)
    if subtitle_path is None or not subtitle_path.exists():
        return []

    subtitle_text = subtitle_path.read_text(encoding="utf-8")
    return [
        CommentarySegmentResponse(**segment.model_dump())
        for segment in parse_srt_to_commentary_segments(subtitle_text)
    ]


def _origins_from_env() -> list[str]:
    configured = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000,http://localhost:4173")
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


app = FastAPI(title="Custerion Collection API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins_from_env(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_RUNS_LOCK = Lock()
_RUNS: dict[str, dict[str, object]] = {}
MAX_RUN_EVENTS = 200


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_run_state(run_id: str, **updates: object) -> None:
    with _RUNS_LOCK:
        current = _RUNS.get(run_id)
        if current is None:
            return
        current.update(updates)
        current["updated_at"] = _now_iso()


def _append_run_event(run_id: str, message: str) -> None:
    cleaned = message.strip()
    if not cleaned:
        return

    with _RUNS_LOCK:
        current = _RUNS.get(run_id)
        if current is None:
            return
        events = current.get("events")
        if not isinstance(events, list):
            events = []
            current["events"] = events
        if events and events[-1] == cleaned:
            return
        events.append(cleaned)
        if len(events) > MAX_RUN_EVENTS:
            del events[:-MAX_RUN_EVENTS]
        current["updated_at"] = _now_iso()


def _run_deep_dive_background(run_id: str, request: DeepDiveRequest) -> None:
    try:
        _set_run_state(run_id, status="running", stage="Preparing execution", progress=10)
        _append_run_event(run_id, "System: Preparing execution")

        def progress(stage: str, pct: int) -> None:
            _set_run_state(run_id, status="running", stage=stage, progress=pct)
            _append_run_event(run_id, f"Stage: {stage} ({pct}%)")

        def event(message: str) -> None:
            _append_run_event(run_id, message)

        result = execute_deep_dive(
            title=request.title,
            suggestion_mode=request.suggest,
            process_mode_override=request.process_mode,
            dry_run=request.dry_run,
            progress_callback=progress,
            event_callback=event,
        )
        _set_run_state(
            run_id,
            status="completed",
            stage="Completed",
            progress=100,
            result=DeepDiveResponse(
                title=result.title,
                status=result.status,
                warnings=result.warnings,
                markdown=result.markdown,
                diagnostics_path=result.diagnostics_path,
                markdown_path=result.markdown_path,
                artifact_json_path=result.artifact_json_path,
                html_path=result.html_path,
            ).model_dump(),
            error=None,
        )
        _append_run_event(run_id, "System: Run completed")
    except ValueError as exc:
        _set_run_state(
            run_id,
            status="failed",
            stage="Failed",
            progress=100,
            error=str(exc),
        )
        _append_run_event(run_id, f"Error: {exc}")
    except Exception as exc:
        logger.exception("Deep-dive background run failed")
        _set_run_state(
            run_id,
            status="failed",
            stage="Failed",
            progress=100,
            error=f"Deep-dive generation failed: {exc}",
        )
        _append_run_event(run_id, f"Error: Deep-dive generation failed: {exc}")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/deep-dive", response_model=DeepDiveResponse)
def create_deep_dive(request: DeepDiveRequest) -> DeepDiveResponse:
    try:
        result = execute_deep_dive(
            title=request.title,
            suggestion_mode=request.suggest,
            process_mode_override=request.process_mode,
            dry_run=request.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Deep-dive generation failed")
        raise HTTPException(status_code=500, detail="Deep-dive generation failed") from exc

    return DeepDiveResponse(
        title=result.title,
        status=result.status,
        warnings=result.warnings,
        markdown=result.markdown,
        diagnostics_path=result.diagnostics_path,
        markdown_path=result.markdown_path,
        artifact_json_path=result.artifact_json_path,
        html_path=result.html_path,
    )


@app.post("/deep-dive/start", response_model=DeepDiveStartResponse)
def start_deep_dive(request: DeepDiveRequest, background_tasks: BackgroundTasks) -> DeepDiveStartResponse:
    run_id = uuid4().hex
    now = _now_iso()
    with _RUNS_LOCK:
        _RUNS[run_id] = {
            "run_id": run_id,
            "status": "queued",
            "stage": "Queued",
            "progress": 0,
            "started_at": now,
            "updated_at": now,
            "events": ["System: Run queued"],
            "result": None,
            "error": None,
        }

    background_tasks.add_task(_run_deep_dive_background, run_id, request)
    return DeepDiveStartResponse(run_id=run_id, status="queued", stage="Queued", progress=0)


@app.get("/deep-dive/{run_id}", response_model=DeepDiveRunStatus)
def get_deep_dive_status(run_id: str) -> DeepDiveRunStatus:
    with _RUNS_LOCK:
        record = _RUNS.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        snapshot = dict(record)

    payload = DeepDiveRunStatus(
        run_id=str(snapshot["run_id"]),
        status=str(snapshot["status"]),
        stage=str(snapshot["stage"]),
        progress=int(snapshot["progress"]),
        started_at=str(snapshot["started_at"]),
        updated_at=str(snapshot["updated_at"]),
        events=[str(item) for item in snapshot.get("events", []) if isinstance(item, str)],
        error=str(snapshot["error"]) if snapshot["error"] else None,
        result=DeepDiveResponse(**snapshot["result"]) if snapshot.get("result") else None,
    )
    return payload


@app.get("/artifacts", response_model=list[ArtifactSummary])
def get_artifacts(limit: int = 20) -> list[ArtifactSummary]:
    bounded_limit = max(1, min(limit, 100))
    raw_items = list_recent_artifacts(limit=bounded_limit)
    return [ArtifactSummary(**item) for item in raw_items]


@app.get("/artifacts/{slug}/html", response_class=HTMLResponse)
def get_artifact_html(slug: str) -> HTMLResponse:
    html_path = latest_html_artifact_for_slug(slug)
    if html_path is None or not html_path.exists():
        raise HTTPException(status_code=404, detail=f"HTML artifact not found for slug: {slug}")
    html = html_path.read_text(encoding="utf-8")
    html = _strip_placeholder_source_links_from_html(html)
    if _tts_enabled():
        html = _inject_tts_controls(html=html, slug=slug)
    return HTMLResponse(content=html)


@app.get("/artifacts/{slug}/tts/voices", response_model=ArtifactTtsVoicesResponse)
def get_artifact_tts_voices(slug: str) -> ArtifactTtsVoicesResponse:
    try:
        default_voice, voices = list_tts_voices_for_slug(slug)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ArtifactTtsVoicesResponse(
        slug=slug,
        model=tts_runtime_label(),
        default_voice=default_voice,
        voices=voices,
    )


@app.get("/artifacts/{slug}/tts/audio")
def get_artifact_tts_audio(
    slug: str,
    voice: str | None = None,
    mode: str = "full",
) -> FileResponse:
    try:
        audio_path = synthesize_tts_audio_for_slug(slug=slug, voice=voice, mode=mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Artifact TTS synthesis failed")
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {exc}") from exc

    media_type = "audio/mpeg" if audio_path.suffix.lower() == ".mp3" else "audio/wav"
    return FileResponse(path=str(audio_path), media_type=media_type, filename=audio_path.name)


@app.get("/artifacts/{slug}/commentary", response_model=ArtifactCommentaryResponse)
def get_artifact_commentary(slug: str) -> ArtifactCommentaryResponse:
    artifact = load_artifact_for_slug(slug)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Artifact not found for slug: {slug}")

    segments = [CommentarySegmentResponse(**segment.model_dump()) for segment in artifact.commentary_segments]
    commentary_mode = artifact.commentary_mode
    if not segments:
        segments = _subtitle_segments_for_slug(slug)
        if segments:
            commentary_mode = "timed"

    duration_ms = 0
    timed = [segment.timestamp_ms for segment in segments if segment.timestamp_ms is not None]
    if timed:
        duration_ms = max(int(ts) for ts in timed)
    elif artifact.film.runtime_minutes:
        duration_ms = artifact.film.runtime_minutes * 60 * 1000

    return ArtifactCommentaryResponse(
        slug=slug,
        title=artifact.film.title,
        commentary_mode=commentary_mode,
        duration_ms=duration_ms,
        segments=segments,
        external_playback={
            "provider": "jellyfin",
            "itemId": artifact.film.external_ids.get("jellyfin_item_id"),
            "positionMs": None,
        },
    )


@app.get("/artifacts/{slug}/commentary/realtime", response_model=ArtifactCommentaryRealtimeResponse)
def get_artifact_commentary_realtime(
    slug: str,
    position_ms: int = 0,
    window_ms: int = 30000,
    limit: int = 6,
) -> ArtifactCommentaryRealtimeResponse:
    artifact = load_artifact_for_slug(slug)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Artifact not found for slug: {slug}")

    segments = [CommentarySegmentResponse(**segment.model_dump()) for segment in artifact.commentary_segments]
    commentary_mode = artifact.commentary_mode
    if not segments:
        segments = _subtitle_segments_for_slug(slug)
        if segments:
            commentary_mode = "timed"

    bounded_position = max(0, position_ms)
    bounded_window = max(1000, min(window_ms, 120000))
    bounded_limit = max(1, min(limit, 20))

    active = None
    upcoming = []
    for segment in segments:
        ts = segment.timestamp_ms
        if ts is None:
            continue
        if ts <= bounded_position:
            active = segment
            continue
        if ts <= bounded_position + bounded_window:
            upcoming.append(segment)
        if len(upcoming) >= bounded_limit:
            break

    return ArtifactCommentaryRealtimeResponse(
        slug=slug,
        commentary_mode=commentary_mode,
        position_ms=bounded_position,
        active_segment=active,
        upcoming_segments=upcoming,
    )


@app.post("/artifacts/{slug}/commentary/subtitles", response_model=CommentarySubtitleImportResponse)
def import_artifact_commentary_subtitles(
    slug: str,
    request: CommentarySubtitleImportRequest,
) -> CommentarySubtitleImportResponse:
    artifact = load_artifact_for_slug(slug)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Artifact not found for slug: {slug}")

    segments = parse_srt_to_commentary_segments(request.subtitle_text)
    if not segments:
        raise HTTPException(status_code=400, detail="No valid subtitle cues found in provided SRT text")

    subtitle_path = upsert_subtitle_artifact_for_slug(slug=slug, subtitle_text=request.subtitle_text)
    markdown_path = latest_markdown_artifact_for_slug(slug)
    report_markdown = markdown_path.read_text(encoding="utf-8") if markdown_path and markdown_path.exists() else ""
    planning_goal = build_commentary_planner_instruction(artifact)

    planned_segments = build_goal_driven_commentary_plan(
        subtitle_text=request.subtitle_text,
        artifact=artifact,
        report_markdown=report_markdown,
    )
    commentary_plan_path = None
    if planned_segments:
        plan_payload = commentary_plan_payload(
            segments=planned_segments,
            goal=planning_goal,
            planner="goal_planner",
        )
        commentary_plan_path = upsert_commentary_plan_artifact_for_slug(slug=slug, payload=plan_payload)

    return CommentarySubtitleImportResponse(
        slug=slug,
        subtitle_path=str(subtitle_path),
        commentary_plan_path=str(commentary_plan_path) if commentary_plan_path else None,
        planning_goal=planning_goal,
        segment_count=len(planned_segments) if planned_segments else len(segments),
        commentary_mode="timed",
    )


@app.post("/artifacts/{slug}/html/regenerate", response_model=HtmlRegenerateResponse)
def regenerate_artifact_html(slug: str) -> HtmlRegenerateResponse:
    markdown_path = latest_markdown_artifact_for_slug(slug)
    if markdown_path is None or not markdown_path.exists():
        raise HTTPException(status_code=404, detail=f"Markdown artifact not found for slug: {slug}")

    markdown = markdown_path.read_text(encoding="utf-8")
    title = artifact_title_for_slug(slug)
    html_content, warning = render_html_report_with_retry(markdown=markdown, selected_title=title)

    if html_content is None:
        detail = warning or "HTML regeneration failed"
        raise HTTPException(status_code=503, detail=detail)

    html_path = upsert_html_artifact_for_slug(slug, html_content)
    return HtmlRegenerateResponse(slug=slug, html_path=str(html_path), warning=warning)
