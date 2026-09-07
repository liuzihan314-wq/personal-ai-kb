"""The fixed document contract used by all input adapters."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UnifiedDocument(BaseModel):
    """A source document normalized for the knowledge-base pipeline.

    Optional source fields intentionally remain nullable because different
    adapters do not provide the same metadata.  Raw immutability is enforced
    by the storage layer rather than by this transport model.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    content_type: str = ""
    title: str = ""
    content: str = ""
    source_type: str = ""
    source_url: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    ingested_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    original_file: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
