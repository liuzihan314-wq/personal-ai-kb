"""Structured results for local, traceable question answering."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pkb.retrieval.model import RetrievalResult


QAStatus = Literal["answered", "no_hits", "insufficient_evidence"]
SourceKind = Literal["knowledge", "note", "raw"]
EvidenceLevel = Literal[
    "none",
    "knowledge",
    "knowledge+notes",
    "knowledge+notes+raw",
    "knowledge+raw",
    "notes",
    "notes+raw",
    "raw",
]


class QASource(BaseModel):
    """One local artifact used by, or linked from, an answer."""

    model_config = ConfigDict(extra="forbid")

    kind: SourceKind
    source_id: str = Field(min_length=1)
    title: str = ""
    path: str | None = None
    reference: str | None = None
    role: str = Field(default="supporting evidence", min_length=1)
    available: bool = True

    @property
    def id(self) -> str:
        """Return the stable source identifier."""

        return self.source_id

    @property
    def identifier(self) -> str:
        """Return the stable source identifier under a descriptive name."""

        return self.source_id

    @property
    def source_type(self) -> SourceKind:
        """Return the artifact kind."""

        return self.kind

    @property
    def source_path(self) -> str | None:
        """Return the local path when one is known."""

        return self.path


class QAEvidence(BaseModel):
    """A human-readable explanation of how one source supports the answer."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    source_kind: SourceKind
    explanation: str = Field(min_length=1)
    excerpt: str | None = None
    path: str | None = None

    @property
    def source_type(self) -> SourceKind:
        """Return the artifact kind."""

        return self.source_kind

    @property
    def source_path(self) -> str | None:
        """Return the local path when one is known."""

        return self.path


class QAResult(BaseModel):
    """The complete, auditable result of one local question."""

    model_config = ConfigDict(extra="forbid")

    question: str
    status: QAStatus
    answer: str | None = None
    evidence_level: EvidenceLevel = "none"
    reason: str = Field(min_length=1)
    retrieval: RetrievalResult
    knowledge_topics: list[str] = Field(default_factory=list)
    sources: list[QASource] = Field(default_factory=list)
    evidence: list[QAEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_answer_state(self) -> "QAResult":
        if self.status == "answered":
            if not self.answer or not self.answer.strip():
                raise ValueError("answered results must contain a non-empty answer")
            if self.evidence_level == "none":
                raise ValueError("answered results must identify an evidence level")
        elif self.answer is not None and not self.answer.strip():
            self.answer = None
        return self

    @property
    def is_answered(self) -> bool:
        """Return whether the result contains a grounded answer."""

        return self.status == "answered"

    @property
    def has_answer(self) -> bool:
        """Compatibility alias for callers that use a boolean answer check."""

        return self.is_answered

    @property
    def no_answer(self) -> bool:
        """Return whether the local evidence was insufficient for an answer."""

        return not self.is_answered

    @property
    def answer_status(self) -> Literal["answered", "no_answer"]:
        """Collapse the detailed state into a simple answer/no-answer status."""

        return "answered" if self.is_answered else "no_answer"

    @property
    def found(self) -> bool:
        """Return whether any answer evidence was found."""

        return self.status == "answered"

    @property
    def answer_text(self) -> str:
        """Return answer text or an empty string for structured no-answer states."""

        return self.answer or ""

    @property
    def source_paths(self) -> list[str]:
        """Return known source paths in stable result order."""

        return [source.path for source in self.sources if source.path]

    @property
    def knowledge_sources(self) -> list[QASource]:
        """Return only Knowledge artifacts."""

        return [source for source in self.sources if source.kind == "knowledge"]

    @property
    def note_sources(self) -> list[QASource]:
        """Return only Note artifacts."""

        return [source for source in self.sources if source.kind == "note"]

    @property
    def raw_sources(self) -> list[QASource]:
        """Return only Raw artifacts."""

        return [source for source in self.sources if source.kind == "raw"]


# Public aliases keep the result layer discoverable under common vocabulary.
AnswerResult = QAResult
QuestionAnswer = QAResult
TopicSynthesisResult = QAResult
EvidenceItem = QAEvidence
TraceableSource = QASource
AnswerStatus = QAStatus


__all__ = [
    "AnswerResult",
    "AnswerStatus",
    "EvidenceItem",
    "EvidenceLevel",
    "QAEvidence",
    "QAResult",
    "QASource",
    "QAStatus",
    "QuestionAnswer",
    "SourceKind",
    "TopicSynthesisResult",
    "TraceableSource",
]
