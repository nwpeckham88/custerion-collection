from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class SourceCitation(BaseModel):
    provider: str
    source_id: str
    url: HttpUrl | None = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
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


class FilmIdentity(BaseModel):
    title: str
    year: int
    runtime_minutes: int | None = None
    language: str | None = None
    canonical_id: str


class DeepDiveArtifact(BaseModel):
    film: FilmIdentity
    personalized_intro: str
    sections: list[DeepDiveSection]
    watch_next: list[str]
    known_unknowns: list[str]
    follow_up_media: list[FollowUpMediaItem]
    citations: list[SourceCitation]
    created_at: datetime = Field(default_factory=datetime.utcnow)
