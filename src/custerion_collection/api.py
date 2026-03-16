from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from custerion_collection.service import execute_deep_dive


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
        raise HTTPException(status_code=500, detail=f"Deep-dive generation failed: {exc}") from exc

    return DeepDiveResponse(
        title=result.title,
        status=result.status,
        warnings=result.warnings,
        markdown=result.markdown,
        diagnostics_path=result.diagnostics_path,
        markdown_path=result.markdown_path,
        artifact_json_path=result.artifact_json_path,
    )
