"""Models for compiled, topic-level knowledge."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class KnowledgeSource(BaseModel):
    """One Note and its preserved path back to the Raw document."""

    model_config = ConfigDict(extra="forbid")

    note_id: str = Field(min_length=1)
    title: str = ""
    raw_document_id: str = ""
    reference: str = Field(min_length=1)

    @model_validator(mode="after")
    def fill_raw_document_id(self) -> "KnowledgeSource":
        self.note_id = self.note_id.strip()
        self.title = " ".join(self.title.split())
        self.reference = self.reference.strip()
        if not self.note_id:
            raise ValueError("note_id cannot be empty")
        if not self.reference:
            raise ValueError("reference cannot be empty")
        self.raw_document_id = self.raw_document_id.strip() or self.note_id
        return self

    @property
    def document_id(self) -> str:
        """Expose the Raw document ID under the name used by other layers."""

        return self.raw_document_id


class TopicKnowledge(BaseModel):
    """The current compiled understanding of one topic.

    ``source_note_ids`` and ``source_references`` are deliberately kept as
    first-class fields so a Knowledge page can be traced without parsing its
    prose.  ``current_judgment`` is accepted as a vocabulary-compatible alias
    for callers that use the product wording; both fields are synchronized.
    """

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    source_note_ids: list[str] = Field(min_length=1)
    source_references: list[str] = Field(min_length=1)
    synthesis: str | None = Field(default=None, min_length=1)
    current_judgment: str | None = Field(default=None, min_length=1)
    sources: list[KnowledgeSource] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_trace_and_content(self) -> "TopicKnowledge":
        self.topic = " ".join(self.topic.split())
        if not self.topic:
            raise ValueError("topic cannot be empty")

        cleaned_ids: list[str] = []
        for value in self.source_note_ids:
            if not isinstance(value, str):
                raise ValueError("source_note_ids must contain strings")
            item = value.strip()
            if not item:
                raise ValueError("source_note_ids cannot contain empty values")
            if item in cleaned_ids:
                raise ValueError(f"duplicate source Note ID: {item}")
            cleaned_ids.append(item)
        self.source_note_ids = cleaned_ids

        cleaned_references: list[str] = []
        for value in self.source_references:
            if not isinstance(value, str):
                raise ValueError("source_references must contain strings")
            item = value.strip()
            if not item:
                raise ValueError("source_references cannot contain empty values")
            cleaned_references.append(item)
        if len(cleaned_references) != len(cleaned_ids):
            raise ValueError("source_note_ids and source_references must align")
        self.source_references = cleaned_references

        content = (self.synthesis or self.current_judgment or "").strip()
        if not content:
            raise ValueError("compiled synthesis cannot be empty")
        self.synthesis = content
        self.current_judgment = content

        if not self.sources:
            self.sources = [
                KnowledgeSource(
                    note_id=note_id,
                    raw_document_id=note_id,
                    reference=reference,
                )
                for note_id, reference in zip(
                    self.source_note_ids,
                    self.source_references,
                    strict=True,
                )
            ]
        else:
            if len(self.sources) != len(self.source_note_ids):
                raise ValueError("sources must align with source_note_ids")
            for source, note_id, reference in zip(
                self.sources,
                self.source_note_ids,
                self.source_references,
                strict=True,
            ):
                if source.note_id != note_id:
                    raise ValueError("sources must preserve source_note_ids order")
                if source.reference != reference:
                    raise ValueError("sources must preserve source_references order")
        return self

    @property
    def source_ids(self) -> list[str]:
        """Short alias for callers that use source IDs generically."""

        return self.source_note_ids

    @property
    def source_refs(self) -> list[str]:
        """Short alias for callers that use source references generically."""

        return self.source_references

    @property
    def current_synthesis(self) -> str:
        """Return the current topic judgment as a non-optional string."""

        return self.synthesis or ""


Knowledge = TopicKnowledge
