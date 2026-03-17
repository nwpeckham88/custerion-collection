from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from custerion_collection.service import execute_deep_dive
from custerion_collection.storage import list_recent_artifacts, latest_html_artifact_for_slug


logger = logging.getLogger(__name__)


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
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
