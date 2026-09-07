"""Adapter for manually captured ideas, quotes, and inspirations."""

from datetime import datetime, timezone
import json
from hashlib import sha256
from pathlib import Path
from typing import Callable, Sequence

from pkb.config import get_settings
from pkb.models import UnifiedDocument
from pkb.storage import RawStorage


class IdeaCardError(ValueError):
    """Raised when an idea card cannot be created under the V1 contract."""


class IdeaCardImporter:
    """Create immutable Raw records for manually entered idea cards."""

    def __init__(
        self,
        raw_storage: RawStorage | None = None,
        *,
        raw_dir: str | Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if raw_storage is not None and raw_dir is not None:
            raise ValueError("Pass raw_storage or raw_dir, not both")
        self.raw_storage = raw_storage or RawStorage(
            raw_dir if raw_dir is not None else get_settings().raw_dir
        )
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def create(
        self,
        content: str,
        *,
        source_url: str | None = None,
        tags: Sequence[str] | None = None,
        note: str | None = None,
    ) -> UnifiedDocument:
        """Create one card, returning the existing Raw document on duplicates."""

        if not isinstance(content, str) or not content.strip():
            raise IdeaCardError("卡片正文不能为空")

        normalized_source_url = source_url.strip() if source_url else None
        normalized_tags = _normalize_tags(tags)
        normalized_note = note if note else None
        identity_payload = {
            "content": content,
            "content_type": "idea",
            "note": normalized_note,
            "source_type": "manual",
            "source_url": normalized_source_url,
            "tags": normalized_tags,
        }
        document_id = sha256(
            json.dumps(
                identity_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        raw_paths = self.raw_storage.paths_for(document_id, content_type="idea")
        content_bytes = content.encode("utf-8")

        metadata = {
            "card_hash": document_id,
            "content_sha256": sha256(content_bytes).hexdigest(),
            "file_size": len(content_bytes),
            "extracted_text_file": str(raw_paths.extracted_text_file),
            "metadata_file": str(raw_paths.metadata_file),
        }
        if normalized_note is not None:
            metadata["note"] = normalized_note

        document = UnifiedDocument(
            id=document_id,
            content_type="idea",
            title="Idea Card",
            content=content,
            source_type="manual",
            source_url=normalized_source_url,
            tags=normalized_tags,
            ingested_at=self.clock(),
            original_file=str(raw_paths.original_file),
            metadata=metadata,
        )
        return self.raw_storage.store(document, content_bytes)


def _normalize_tags(tags: Sequence[str] | None) -> list[str]:
    """Return stable, non-empty tags while preserving their input order."""

    if tags is None:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if not isinstance(tag, str):
            raise IdeaCardError("tags 必须是文本")
        value = tag.strip()
        if value and value not in seen:
            normalized.append(value)
            seen.add(value)
    return normalized


def create_idea(
    content: str,
    *,
    source_url: str | None = None,
    tags: Sequence[str] | None = None,
    note: str | None = None,
    raw_dir: str | Path | None = None,
) -> UnifiedDocument:
    """Create one manual idea card using the configured Raw directory."""

    return IdeaCardImporter(raw_dir=raw_dir).create(
        content,
        source_url=source_url,
        tags=tags,
        note=note,
    )
