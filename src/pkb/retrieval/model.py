"""Models for deterministic, explainable Index retrieval."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RetrievalField = Literal[
    "title",
    "tags",
    "keywords",
    "topic",
    "semantic",
    "related",
]
RetrievalStatus = Literal["ok", "no_hits"]


class RetrievalEvidence(BaseModel):
    """Field-level values that matched a retrieval query."""

    model_config = ConfigDict(extra="forbid")

    title: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    topic: list[str] = Field(default_factory=list)
    semantic: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)

    @property
    def matched_fields(self) -> tuple[str, ...]:
        """Return evidence fields in the stable scoring order."""

        return tuple(
            field
            for field in ("title", "tags", "keywords", "topic", "semantic", "related")
            if getattr(self, field)
        )

    @property
    def is_empty(self) -> bool:
        """Return whether this candidate contains no field evidence."""

        return not self.matched_fields


class RetrievalReason(BaseModel):
    """One explainable contribution to a candidate score."""

    model_config = ConfigDict(extra="forbid")

    field: RetrievalField
    matches: list[str] = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(min_length=1)

    @property
    def weight(self) -> float:
        """Compatibility name for callers that use scoring terminology."""

        return self.score

    @property
    def reason(self) -> str:
        """Compatibility name matching the persisted Related model."""

        return self.explanation


class RetrievalCandidate(BaseModel):
    """One ranked Note candidate returned by the local Index search."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    raw_document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    note_path: str = Field(min_length=1)
    evidence: RetrievalEvidence
    reasons: list[RetrievalReason] = Field(min_length=1)

    @property
    def path(self) -> str:
        """Return the persisted Note path."""

        return self.note_path

    @property
    def source_path(self) -> str:
        """Return the candidate's traceable Note source path."""

        return self.note_path


class RetrievalResult(BaseModel):
    """The complete result of one local Index retrieval operation."""

    model_config = ConfigDict(extra="forbid")

    query: str
    status: RetrievalStatus
    candidates: list[RetrievalCandidate] = Field(default_factory=list)

    @property
    def results(self) -> list[RetrievalCandidate]:
        """Alternative result-oriented name for the candidate list."""

        return self.candidates

    @property
    def hits(self) -> list[RetrievalCandidate]:
        """Return the candidates that matched the query."""

        return self.candidates

    @property
    def found(self) -> bool:
        """Return whether at least one candidate was found."""

        return bool(self.candidates)

    @property
    def is_empty(self) -> bool:
        """Return whether this result has no candidates."""

        return not self.candidates


class CandidateJudgmentRequest(BaseModel):
    """Future AI-judgment input boundary; no Provider is invoked here."""

    model_config = ConfigDict(extra="forbid")

    query: str
    candidates: list[RetrievalCandidate] = Field(default_factory=list)


# Public aliases keep the small DTO layer discoverable under common names.
SearchCandidate = RetrievalCandidate
SearchResult = RetrievalResult
