"""Structured results for local, traceable spoken-script generation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pkb.retrieval.model import RetrievalResult
from pkb.topics.model import TopicCandidate


ScriptStatus = Literal[
    "generated",
    "not_confirmed",
    "no_hits",
    "insufficient_evidence",
]
ScriptSourceKind = Literal["knowledge", "note", "raw"]


class ScriptSelection(BaseModel):
    """The topic selection state carried through one script request."""

    model_config = ConfigDict(extra="forbid")

    confirmed: bool = False
    topic: str | None = None
    identifier: str | None = None
    candidate: TopicCandidate | None = None

    @model_validator(mode="after")
    def clean_values(self) -> "ScriptSelection":
        if self.topic is not None:
            self.topic = " ".join(self.topic.split()) or None
        if self.identifier is not None:
            self.identifier = " ".join(self.identifier.split()) or None
        if self.candidate is not None:
            self.topic = self.topic or self.candidate.title
            self.identifier = self.identifier or self.candidate.title
        if self.confirmed and not self.topic:
            raise ValueError("a confirmed selection must contain a topic")
        return self

    @property
    def selected_topic(self) -> str | None:
        """Return the selected topic title when one was supplied."""

        return self.topic

    @property
    def user_confirmed(self) -> bool:
        """Expose confirmation using the product's wording."""

        return self.confirmed


class ScriptSource(BaseModel):
    """One local Knowledge, Note, or Raw artifact used by a script."""

    model_config = ConfigDict(extra="forbid")

    kind: ScriptSourceKind
    source_id: str = Field(min_length=1)
    title: str = ""
    path: str | None = None
    reference: str | None = None
    role: str = Field(default="supporting evidence", min_length=1)
    available: bool = True

    @model_validator(mode="after")
    def clean_values(self) -> "ScriptSource":
        self.source_id = self.source_id.strip()
        self.title = " ".join(self.title.split())
        self.path = self.path.strip() if self.path else None
        self.reference = self.reference.strip() if self.reference else None
        self.role = " ".join(self.role.split())
        if not self.source_id:
            raise ValueError("source_id cannot be empty")
        return self

    @property
    def id(self) -> str:
        """Return the stable source identifier."""

        return self.source_id

    @property
    def source_type(self) -> ScriptSourceKind:
        """Return the artifact kind."""

        return self.kind

    @property
    def source_path(self) -> str | None:
        """Return the local path when one is known."""

        return self.path


class ScriptEvidence(BaseModel):
    """A grounded excerpt explaining how an artifact supports the script."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    source_kind: ScriptSourceKind
    explanation: str = Field(min_length=1)
    excerpt: str | None = None
    path: str | None = None

    @model_validator(mode="after")
    def clean_values(self) -> "ScriptEvidence":
        self.source_id = self.source_id.strip()
        self.explanation = " ".join(self.explanation.split())
        self.excerpt = " ".join(self.excerpt.split()) if self.excerpt else None
        self.path = self.path.strip() if self.path else None
        if not self.source_id:
            raise ValueError("source_id cannot be empty")
        if not self.explanation:
            raise ValueError("explanation cannot be empty")
        return self

    @property
    def source_type(self) -> ScriptSourceKind:
        """Return the artifact kind."""

        return self.source_kind

    @property
    def source_path(self) -> str | None:
        """Return the local path when one is known."""

        return self.path


class ScriptResult(BaseModel):
    """The complete result of one local spoken-script request."""

    model_config = ConfigDict(extra="forbid")

    topic: str | None = None
    title: str | None = None
    status: ScriptStatus
    selection_confirmed: bool = False
    selection: ScriptSelection
    script: str | None = None
    message: str = Field(min_length=1)
    retrieval: RetrievalResult
    sources: list[ScriptSource] = Field(default_factory=list)
    evidence: list[ScriptEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_state(self) -> "ScriptResult":
        self.topic = " ".join(self.topic.split()) if self.topic else None
        self.title = " ".join(self.title.split()) if self.title else None
        if self.selection_confirmed and not self.selection.confirmed:
            self.selection.confirmed = True
        self.selection_confirmed = self.selection.confirmed
        if self.topic is None:
            self.topic = self.selection.topic
        if self.status == "generated":
            if not self.selection_confirmed:
                raise ValueError("generated scripts require a confirmed selection")
            if not self.script or not self.script.strip():
                raise ValueError("generated results must contain a script")
            if not self.evidence:
                raise ValueError("generated results must contain evidence")
        elif self.script is not None and not self.script.strip():
            self.script = None
        return self

    @property
    def selected_topic(self) -> str | None:
        """Return the selected topic title."""

        return self.topic

    @property
    def script_text(self) -> str:
        """Return script text or an empty string for non-generated states."""

        return self.script or ""

    @property
    def body(self) -> str:
        """Compatibility alias for the spoken body."""

        return self.script_text

    @property
    def content(self) -> str:
        """Compatibility alias for callers that use content terminology."""

        return self.script_text

    @property
    def reason(self) -> str:
        """Return the structured explanation under the Q&A-style name."""

        return self.message

    @property
    def has_script(self) -> bool:
        """Return whether a script was generated."""

        return self.status == "generated" and bool(self.script_text)

    @property
    def is_generated(self) -> bool:
        """Return whether the result is a successful generation."""

        return self.has_script

    @property
    def source_paths(self) -> list[str]:
        """Return available local source paths in result order."""

        return [source.path for source in self.sources if source.path]

    @property
    def evidence_level(self) -> str:
        """Return a stable summary of the artifact kinds used."""

        kinds = {source.kind for source in self.sources if source.available}
        return "+".join(
            kind for kind in ("knowledge", "notes", "raw")
            if (kind == "notes" and "note" in kinds) or kind in kinds
        ) or "none"

    @property
    def knowledge_sources(self) -> list[ScriptSource]:
        """Return only Knowledge sources."""

        return [source for source in self.sources if source.kind == "knowledge"]

    @property
    def note_sources(self) -> list[ScriptSource]:
        """Return only Note sources."""

        return [source for source in self.sources if source.kind == "note"]

    @property
    def raw_sources(self) -> list[ScriptSource]:
        """Return only Raw sources."""

        return [source for source in self.sources if source.kind == "raw"]


# Keep common vocabulary discoverable to callers of the small DTO layer.
ScriptGenerationResult = ScriptResult
ScriptWriterResult = ScriptResult
ScriptGenerationStatus = ScriptStatus
TraceableScriptSource = ScriptSource
ScriptEvidenceItem = ScriptEvidence


__all__ = [
    "ScriptEvidence",
    "ScriptEvidenceItem",
    "ScriptGenerationResult",
    "ScriptGenerationStatus",
    "ScriptResult",
    "ScriptSelection",
    "ScriptSource",
    "ScriptSourceKind",
    "ScriptStatus",
    "ScriptWriterResult",
    "TraceableScriptSource",
]
