"""Models for single-document AI notes."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class Note(BaseModel):
    """The persisted, single-document understanding result."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    tags: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    key_points: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)
    content_type: str = ""
    source_url: str | None = None
    original_file: str | None = None
    source_reference: str = ""
    original_content: str | None = None
    user_note: str | None = None
