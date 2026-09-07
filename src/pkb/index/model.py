"""Models for the local, rebuildable JSON index."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


INDEX_SCHEMA_VERSION = 1


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RelatedReason(BaseModel):
    """One deterministic rule that contributed to a related-document link."""

    model_config = ConfigDict(extra="forbid")

    rule: str = Field(min_length=1)
    matches: list[str] = Field(min_length=1)
    weight: float = Field(ge=0.0, le=1.0)


class RelatedEntry(BaseModel):
    """A related Note with a score and human-readable explanation."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    reasons: list[RelatedReason] = Field(min_length=1)


class IndexEntry(BaseModel):
    """The fields needed to locate and pre-filter one persisted Note."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    created_at: datetime | None = None
    content_type: str = ""
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    source_type: str = Field(min_length=1)
    note_path: str = Field(min_length=1)
    # Topic generation belongs to a later task.  Keeping the field explicit
    # makes that boundary visible without inventing an AI conclusion here.
    topic: str | None = None
    related: list[RelatedEntry] = Field(default_factory=list)

    @property
    def path(self) -> str:
        """Return the persisted Note path under the familiar short name."""

        return self.note_path


class IndexFile(BaseModel):
    """Complete contents of the V1 local JSON index."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[INDEX_SCHEMA_VERSION] = INDEX_SCHEMA_VERSION
    generated_at: datetime = Field(default_factory=_utc_now)
    notes_dir: str = Field(min_length=1)
    entries: list[IndexEntry] = Field(default_factory=list)

    @property
    def documents(self) -> list[IndexEntry]:
        """Return entries under the alternative document-oriented name."""

        return self.entries

    @property
    def related_count(self) -> int:
        """Return the number of directed related links in the index."""

        return sum(len(entry.related) for entry in self.entries)


# Public aliases keep the model discoverable for callers that use either the
# file-oriented or service-oriented terminology.
LocalIndex = IndexFile
IndexDocument = IndexFile
RelatedLink = RelatedEntry
