"""Structured history records stored inside one user's isolated root."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


HistoryKind = Literal["qa", "topic", "script"]


class HistoryRecord(BaseModel):
    """One auditable operation result.

    Records keep only the operation type, time, result status, and the
    minimal user-facing labels needed to reconstruct *which* question, topic,
    or script the status refers to.  Full answers, scripts, sources, and
    provider content are intentionally not copied here; they remain in their
    existing user-scoped stores.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: HistoryKind
    created_at: datetime
    status: str = Field(min_length=1)
    question: str | None = None
    topic: str | None = None
    candidate_titles: list[str] = Field(default_factory=list)
    script_title: str | None = None
    message: str = Field(min_length=1)

    @model_validator(mode="after")
    def normalize_text(self) -> "HistoryRecord":
        """Normalize user-visible labels without changing record identity."""

        self.id = self.id.strip()
        self.status = " ".join(self.status.split())
        self.message = " ".join(self.message.split())
        self.question = _clean_optional(self.question)
        self.topic = _clean_optional(self.topic)
        self.script_title = _clean_optional(self.script_title)
        self.candidate_titles = [
            value.strip()
            for value in self.candidate_titles
            if isinstance(value, str) and value.strip()
        ]
        if not self.id:
            raise ValueError("history record id cannot be empty")
        if not self.status:
            raise ValueError("history record status cannot be empty")
        if not self.message:
            raise ValueError("history record message cannot be empty")
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=timezone.utc)
        else:
            self.created_at = self.created_at.astimezone(timezone.utc)
        return self


def _clean_optional(value: str | None) -> str | None:
    """Return a non-empty normalized string or ``None``."""

    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None


__all__ = ["HistoryKind", "HistoryRecord"]
