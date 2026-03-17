from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class SourceCitation(BaseModel):
    provider: str
    source_id: str
    url: HttpUrl | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = Field(ge=0.0, le=1.0)
    claim_ref: str


class FollowUpMediaItem(BaseModel):
    kind: Literal["video", "article", "related_film"]
    title: str
    url: HttpUrl | None = None
    rationale: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    source_confidence: float = Field(ge=0.0, le=1.0)


class DeepDiveSection(BaseModel):
    name: str
    content: str
    confidence: float = Field(ge=0.0, le=1.0)


class CommentarySegment(BaseModel):
    order_index: int = Field(ge=0)
    timestamp_ms: int | None = Field(default=None, ge=0)
    scene_label: str
    commentary: str
    source: str | None = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class FilmIdentity(BaseModel):
    title: str
    year: int
    key_credits: list[str] = Field(default_factory=list)
    runtime_minutes: int | None = None
    language: str | None = None
    canonical_id: str
    external_ids: dict[str, str] = Field(default_factory=dict)


class DeepDiveArtifact(BaseModel):
    film: FilmIdentity
    personalized_intro: str
    sections: list[DeepDiveSection]
    commentary_segments: list[CommentarySegment] = Field(default_factory=list)
    commentary_mode: Literal["timed", "untimed", "mixed", "none"] = "none"
    watch_next: list[str]
    known_unknowns: list[str]
    follow_up_media: list[FollowUpMediaItem]
    citations: list[SourceCitation]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_follow_up_media(self) -> "DeepDiveArtifact":
        if len(self.follow_up_media) > 8:
            raise ValueError("follow_up_media cannot exceed 8 items")

        kind_counts: dict[str, int] = {}
        seen_urls: set[str] = set()
        for item in self.follow_up_media:
            kind_counts[item.kind] = kind_counts.get(item.kind, 0) + 1
            if kind_counts[item.kind] > 3:
                raise ValueError(f"follow_up_media kind '{item.kind}' cannot exceed 3 items")

            if item.url is not None:
                key = str(item.url)
                if key in seen_urls:
                    raise ValueError("follow_up_media cannot contain duplicate URLs")
                seen_urls.add(key)

        return self


def deep_dive_artifact_json_schema() -> dict:
    """Return JSON schema for the persisted deep-dive artifact contract."""
    return DeepDiveArtifact.model_json_schema()


class RunDiagnostics(BaseModel):
    run_id: str
    title: str
    suggestion_mode: bool
    status: Literal["success", "degraded", "failed"]
    started_at: datetime
    finished_at: datetime
    duration_ms: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    source_count: int = Field(ge=0, default=0)
    citation_coverage_ratio: float = Field(ge=0.0, le=1.0, default=0.0)
