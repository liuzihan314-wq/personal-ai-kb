"""Models for deterministic, traceable content-topic candidates."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


TopicSourceKind = Literal["knowledge", "note"]


class TopicSource(BaseModel):
    """One persisted Knowledge or Note source supporting a topic candidate."""

    model_config = ConfigDict(extra="forbid")

    kind: TopicSourceKind
    source_id: str = Field(min_length=1)
    title: str = ""
    path: str = Field(min_length=1)
    reference: str = ""
    content_type: str = ""

    @model_validator(mode="after")
    def clean_values(self) -> "TopicSource":
        self.source_id = self.source_id.strip()
        self.title = " ".join(self.title.split())
        self.path = self.path.strip()
        self.reference = self.reference.strip()
        self.content_type = self.content_type.strip()
        if not self.source_id:
            raise ValueError("source_id cannot be empty")
        if not self.path:
            raise ValueError("path cannot be empty")
        return self

    @property
    def id(self) -> str:
        """Expose the stable source ID under the shorter name."""

        return self.source_id

    @property
    def source_path(self) -> str:
        """Return the persisted or stable fallback source path."""

        return self.path

    @property
    def document_id(self) -> str:
        """Expose a Note-like ID for callers handling mixed sources."""

        return self.source_id


class TopicEvidence(BaseModel):
    """One visible signal and the sources in which it was observed."""

    model_config = ConfigDict(extra="forbid")

    signal: str = Field(min_length=1)
    values: list[str] = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def clean_values(self) -> "TopicEvidence":
        self.signal = self.signal.strip()
        self.values = [" ".join(value.split()) for value in self.values if value.strip()]
        self.source_ids = [value.strip() for value in self.source_ids if value.strip()]
        self.explanation = " ".join(self.explanation.split())
        if not self.signal:
            raise ValueError("signal cannot be empty")
        if not self.values:
            raise ValueError("values cannot be empty")
        if not self.source_ids:
            raise ValueError("source_ids cannot be empty")
        if not self.explanation:
            raise ValueError("explanation cannot be empty")
        return self

    @property
    def matches(self) -> list[str]:
        """Compatibility alias for evidence values."""

        return self.values


class TopicReason(BaseModel):
    """One deterministic scoring rule contributing to a candidate."""

    model_config = ConfigDict(extra="forbid")

    rule: str = Field(min_length=1)
    matches: list[str] = Field(min_length=1)
    weight: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(min_length=1)

    @property
    def score(self) -> float:
        """Compatibility name for callers using score terminology."""

        return self.weight

    @property
    def reason(self) -> str:
        """Compatibility alias for the human-readable explanation."""

        return self.explanation


class TopicCandidate(BaseModel):
    """One ranked content topic candidate with auditable support."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    why_worth_doing: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    sources: list[TopicSource] = Field(min_length=1)
    evidence: list[TopicEvidence] = Field(min_length=2)
    reasons: list[TopicReason] = Field(min_length=1)

    @model_validator(mode="after")
    def clean_text(self) -> "TopicCandidate":
        self.title = " ".join(self.title.split())
        self.why_worth_doing = " ".join(self.why_worth_doing.split())
        if not self.title:
            raise ValueError("title cannot be empty")
        if not self.why_worth_doing:
            raise ValueError("why_worth_doing cannot be empty")
        return self

    @property
    def rationale(self) -> str:
        """Compatibility alias for the candidate's reason to make it."""

        return self.why_worth_doing

    @property
    def reason(self) -> str:
        """Compatibility alias matching common candidate vocabulary."""

        return self.why_worth_doing

    @property
    def supporting_sources(self) -> list[TopicSource]:
        """Return the traceable sources supporting this candidate."""

        return self.sources

    @property
    def source_ids(self) -> list[str]:
        """Return stable IDs for all supporting sources."""

        return [source.source_id for source in self.sources]

    @property
    def source_paths(self) -> list[str]:
        """Return paths or stable path fallbacks for all sources."""

        return [source.path for source in self.sources]


TopicGenerationStatus = Literal["ok", "insufficient_data"]


class TopicGenerationResult(BaseModel):
    """The complete result of one local topic-generation operation."""

    model_config = ConfigDict(extra="forbid")

    status: TopicGenerationStatus
    candidates: list[TopicCandidate] = Field(default_factory=list)
    message: str = Field(min_length=1)

    @property
    def results(self) -> list[TopicCandidate]:
        """Alternative result-oriented name for the candidate list."""

        return self.candidates

    @property
    def topics(self) -> list[TopicCandidate]:
        """Alternative topic-oriented name for the candidate list."""

        return self.candidates

    @property
    def found(self) -> bool:
        """Return whether at least one candidate was produced."""

        return bool(self.candidates)

    @property
    def is_empty(self) -> bool:
        """Return whether no candidate is available."""

        return not self.candidates


# Public aliases keep the DTO layer discoverable under common names.
TopicSignal = TopicEvidence
TopicCandidateReason = TopicReason
TopicCandidateSource = TopicSource
GenerateTopicsResult = TopicGenerationResult


__all__ = [
    "GenerateTopicsResult",
    "TopicCandidate",
    "TopicCandidateReason",
    "TopicCandidateSource",
    "TopicEvidence",
    "TopicGenerationResult",
    "TopicGenerationStatus",
    "TopicReason",
    "TopicSignal",
    "TopicSource",
    "TopicSourceKind",
]
