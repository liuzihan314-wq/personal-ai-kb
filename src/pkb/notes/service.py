"""Single-document AI processing and Note persistence."""

from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pkb.config import get_settings
from pkb.models import UnifiedDocument
from pkb.notes.model import Note
from pkb.notes.storage import NoteRecord, NoteStorage
from pkb.providers import AIProvider, MockAIProvider, ProviderDocument


class NoteGenerationError(ValueError):
    """Raised when a provider cannot produce a valid single-document Note."""


def _clean_values(values: Sequence[str], field_name: str) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise NoteGenerationError(f"Provider returned invalid {field_name}")
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise NoteGenerationError(f"Provider returned invalid {field_name}")
        normalized = value.strip()
        if normalized and normalized not in seen:
            cleaned.append(normalized)
            seen.add(normalized)
    return cleaned


def _merge_values(*groups: Sequence[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            if value not in seen:
                merged.append(value)
                seen.add(value)
    return merged


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class NoteService:
    """Generate and persist one traceable Note for one UnifiedDocument."""

    def __init__(
        self,
        provider: AIProvider | None = None,
        note_storage: NoteStorage | None = None,
        *,
        notes_dir: str | Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if note_storage is not None and notes_dir is not None:
            raise ValueError("Pass note_storage or notes_dir, not both")
        self.provider = provider if provider is not None else MockAIProvider()
        self.note_storage = note_storage or NoteStorage(
            notes_dir if notes_dir is not None else get_settings().notes_dir
        )
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def generate(self, document: UnifiedDocument) -> NoteRecord:
        """Generate a Note once; repeated calls return the existing Note."""

        if not isinstance(document, UnifiedDocument):
            raise NoteGenerationError("document must be a UnifiedDocument")

        existing = self.note_storage.read_if_exists(document.id)
        if existing is not None:
            return existing

        source_type = (document.source_type or document.content_type or "unknown").strip()
        title = (document.title or "").strip() or (
            "Idea Card" if document.content_type == "idea" else "Untitled document"
        )
        source_reference = (
            (document.source_url or "").strip()
            or (document.original_file or "").strip()
            or f"raw:{document.id}"
        )
        provider_document = ProviderDocument(
            document_id=document.id,
            title=title,
            content=document.content,
            source=source_reference,
        )

        summary = self._summary(provider_document, document.content)
        key_points = _clean_values(
            self.provider.extract_key_points(provider_document),
            "key points",
        )
        quotes = _clean_values(
            self.provider.extract_quotes(provider_document),
            "quotes",
        )
        generated_tags = _clean_values(
            self.provider.generate_tags(provider_document),
            "tags",
        )
        tags = _merge_values(
            _clean_values(document.tags, "document tags"),
            generated_tags,
        )

        metadata_note = document.metadata.get("note")
        user_note = metadata_note.strip() if isinstance(metadata_note, str) else None
        note = Note(
            document_id=document.id,
            source_type=source_type,
            title=title,
            created_at=_utc(self.clock()),
            tags=tags,
            summary=summary,
            key_points=key_points,
            quotes=quotes,
            content_type=document.content_type,
            source_url=document.source_url,
            original_file=document.original_file,
            source_reference=source_reference,
            original_content=document.content if document.content_type == "idea" else None,
            user_note=user_note or None,
        )
        return self.note_storage.write(note)

    def _summary(self, provider_document: ProviderDocument, fallback: str) -> str:
        summary = self.provider.summarize(provider_document)
        if not isinstance(summary, str):
            raise NoteGenerationError("Provider returned invalid summary")
        normalized = summary.strip()
        if normalized:
            return normalized
        fallback = fallback.strip()
        if fallback:
            return fallback
        raise NoteGenerationError("Provider returned an empty summary")


# Aliases keep the service usable under the names used by the task brief.
NoteGenerator = NoteService
SingleDocumentNoteService = NoteService
NoteGenerationResult = NoteRecord


def generate_note(
    document: UnifiedDocument,
    *,
    provider: AIProvider | None = None,
    note_storage: NoteStorage | None = None,
    notes_dir: str | Path | None = None,
    clock: Callable[[], datetime] | None = None,
) -> NoteRecord:
    """Generate one Note using configured local storage and a provider."""

    return NoteService(
        provider=provider,
        note_storage=note_storage,
        notes_dir=notes_dir,
        clock=clock,
    ).generate(document)
