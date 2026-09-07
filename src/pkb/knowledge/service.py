"""Compile Notes into traceable Topic Knowledge pages."""

from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeAlias

from pkb.config import get_settings
from pkb.index.model import IndexEntry, IndexFile
from pkb.index.storage import IndexStorageError, read_index
from pkb.knowledge.model import KnowledgeSource, TopicKnowledge
from pkb.knowledge.storage import (
    KnowledgeRecord,
    KnowledgeStorage,
    KnowledgeStorageError,
    normalize_topic,
)
from pkb.notes.markdown import NoteFormatError, parse_note
from pkb.notes.model import Note
from pkb.notes.storage import NoteRecord, NoteStorage
from pkb.providers import AIProvider, MockAIProvider, ProviderDocument


class KnowledgeCompilationError(ValueError):
    """Raised when Notes cannot produce trustworthy Topic Knowledge."""


NoteInput: TypeAlias = Note | NoteRecord | IndexEntry | str | Path
NotesInput: TypeAlias = NoteInput | Sequence[NoteInput] | IndexFile


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class KnowledgeCompiler:
    """Compile a selected set of persisted Notes for one topic.

    The compiler only reads Notes and Index data.  The only write performed by
    this service is replacement of the derived Knowledge page.
    """

    def __init__(
        self,
        provider: AIProvider | None = None,
        knowledge_storage: KnowledgeStorage | None = None,
        *,
        storage: KnowledgeStorage | None = None,
        note_storage: NoteStorage | None = None,
        notes_dir: str | Path | None = None,
        knowledge_dir: str | Path | None = None,
        index: IndexFile | str | Path | None = None,
        index_path: str | Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if knowledge_storage is not None and storage is not None:
            raise ValueError("Pass knowledge_storage or storage, not both")
        if (knowledge_storage is not None or storage is not None) and knowledge_dir is not None:
            raise ValueError("Pass storage or knowledge_dir, not both")
        if note_storage is not None and notes_dir is not None:
            raise ValueError("Pass note_storage or notes_dir, not both")
        if index is not None and index_path is not None:
            raise ValueError("Pass index or index_path, not both")
        self.provider = provider if provider is not None else MockAIProvider()
        self.knowledge_storage = knowledge_storage or storage or KnowledgeStorage(
            knowledge_dir if knowledge_dir is not None else get_settings().knowledge_dir
        )
        self.storage = self.knowledge_storage
        self.note_storage = note_storage
        self.notes_dir = (
            Path(notes_dir)
            if notes_dir is not None
            else (note_storage.notes_dir if note_storage is not None else None)
        )
        self.index = self._load_index(index if index is not None else index_path)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _load_index(index: IndexFile | str | Path | None) -> IndexFile | None:
        if index is None:
            return None
        if isinstance(index, IndexFile):
            return index
        try:
            return read_index(index)
        except (FileNotFoundError, IndexStorageError) as exc:
            raise KnowledgeCompilationError(f"Could not read Index: {index}") from exc

    def _scan_note_paths(self) -> list[Path]:
        if self.notes_dir is None:
            raise KnowledgeCompilationError(
                "No Notes input was provided; pass notes or configure notes_dir"
            )
        if not self.notes_dir.exists():
            raise KnowledgeCompilationError(
                f"Notes directory does not exist: {self.notes_dir}"
            )
        if not self.notes_dir.is_dir():
            raise KnowledgeCompilationError(
                f"Notes path is not a directory: {self.notes_dir}"
            )
        return sorted(
            (path for path in self.notes_dir.rglob("*.md") if path.is_file()),
            key=lambda path: path.as_posix(),
        )

    @staticmethod
    def _read_note_path(path: Path) -> Note:
        try:
            markdown = path.read_text(encoding="utf-8")
            return parse_note(markdown)
        except FileNotFoundError:
            raise
        except (OSError, UnicodeError, NoteFormatError) as exc:
            raise KnowledgeCompilationError(f"Invalid Note file: {path}") from exc

    def _note_from_input(self, value: NoteInput, *, index_notes_dir: Path | None) -> Note:
        if isinstance(value, Note):
            return value
        if isinstance(value, NoteRecord):
            return value.note
        if isinstance(value, IndexEntry):
            path = Path(value.note_path)
            if not path.is_file() and not path.is_absolute() and index_notes_dir is not None:
                path = index_notes_dir / path.name
            try:
                note = self._read_note_path(path)
            except FileNotFoundError as exc:
                raise KnowledgeCompilationError(
                    f"Index Note path does not exist: {path}"
                ) from exc
            if note.document_id != value.document_id:
                raise KnowledgeCompilationError(
                    f"Index Note ID does not match its file: {path}"
                )
            return note
        if isinstance(value, (str, Path)):
            path = Path(value)
            try:
                return self._read_note_path(path)
            except FileNotFoundError as exc:
                raise KnowledgeCompilationError(f"Note file does not exist: {path}") from exc
        raise KnowledgeCompilationError(
            f"Unsupported Notes input: {type(value).__name__}"
        )

    def _resolve_notes(self, notes: NotesInput | None) -> list[Note]:
        source: Any = notes
        index_notes_dir: Path | None = self.notes_dir
        if source is None:
            if self.index is not None:
                source = self.index
                index_notes_dir = Path(self.index.notes_dir)
            else:
                source = self._scan_note_paths()

        if isinstance(source, IndexFile):
            values: Iterable[NoteInput] = source.entries
            index_notes_dir = Path(source.notes_dir)
        elif isinstance(source, (Note, NoteRecord, IndexEntry, str, Path)):
            values = [source]
        else:
            try:
                values = source
                iter(values)
            except TypeError as exc:
                raise KnowledgeCompilationError(
                    "Notes input must be Note objects, Note paths, or an Index"
                ) from exc

        resolved: list[Note] = []
        seen_ids: set[str] = set()
        for value in values:
            note = self._note_from_input(value, index_notes_dir=index_notes_dir)
            if note.document_id in seen_ids:
                raise KnowledgeCompilationError(
                    f"Duplicate source Note ID: {note.document_id}"
                )
            seen_ids.add(note.document_id)
            resolved.append(note)
        if not resolved:
            raise KnowledgeCompilationError("No Notes were provided for compilation")
        return resolved

    @staticmethod
    def _source_reference(note: Note) -> str:
        return note.source_reference.strip() or f"raw:{note.document_id}"

    @classmethod
    def _provider_document(cls, note: Note) -> ProviderDocument:
        """Build provider context solely from persisted Note fields."""

        reference = cls._source_reference(note)
        sections = [f"Title: {note.title}", f"Summary: {note.summary}"]
        if note.key_points:
            sections.append(
                "Key points:\n" + "\n".join(f"- {item}" for item in note.key_points)
            )
        if note.quotes:
            sections.append(
                "Quotes:\n" + "\n".join(f'- "{item}"' for item in note.quotes)
            )
        if note.original_content:
            sections.append(f"Original idea:\n{note.original_content}")
        if note.user_note:
            sections.append(f"Personal note:\n{note.user_note}")
        return ProviderDocument(
            document_id=note.document_id,
            title=note.title,
            content="\n\n".join(sections),
            source=reference,
        )

    def compile(self, topic: str, notes: NotesInput | None = None) -> KnowledgeRecord:
        """Compile Notes into a new or updated Topic Knowledge page."""

        try:
            normalized_topic = normalize_topic(topic)
        except (TypeError, KnowledgeStorageError) as exc:
            raise KnowledgeCompilationError(str(exc)) from exc

        selected_notes = self._resolve_notes(notes)
        existing = self.knowledge_storage.read_if_exists(normalized_topic)
        provider_documents = tuple(
            self._provider_document(note) for note in selected_notes
        )
        try:
            synthesis = self.provider.compile_topic(
                normalized_topic,
                provider_documents,
            )
        except Exception as exc:
            raise KnowledgeCompilationError(
                f"Provider could not compile topic {normalized_topic!r}"
            ) from exc
        if not isinstance(synthesis, str) or not synthesis.strip():
            raise KnowledgeCompilationError(
                "Provider returned an empty or invalid topic synthesis"
            )

        sources = [
            KnowledgeSource(
                note_id=note.document_id,
                raw_document_id=note.document_id,
                title=note.title,
                reference=self._source_reference(note),
            )
            for note in selected_notes
        ]
        now = _utc(self.clock())
        knowledge = TopicKnowledge(
            topic=existing.knowledge.topic if existing is not None else normalized_topic,
            created_at=(existing.knowledge.created_at if existing is not None else now),
            updated_at=now,
            source_note_ids=[source.note_id for source in sources],
            source_references=[source.reference for source in sources],
            synthesis=synthesis.strip(),
            sources=sources,
        )
        return self.knowledge_storage.write(knowledge)

    compile_topic = compile
    compile_from_notes = compile
    update = compile
    update_topic = compile
    build = compile
    rebuild = compile


KnowledgeService = KnowledgeCompiler
TopicKnowledgeCompiler = KnowledgeCompiler
KnowledgeCompilationResult = KnowledgeRecord


def compile_topic(
    topic: str,
    notes: NotesInput | None = None,
    *,
    provider: AIProvider | None = None,
    knowledge_storage: KnowledgeStorage | None = None,
    storage: KnowledgeStorage | None = None,
    note_storage: NoteStorage | None = None,
    notes_dir: str | Path | None = None,
    knowledge_dir: str | Path | None = None,
    index: IndexFile | str | Path | None = None,
    index_path: str | Path | None = None,
    clock: Callable[[], datetime] | None = None,
) -> KnowledgeRecord:
    """Compile one topic using local Notes and derived Knowledge storage."""

    return KnowledgeCompiler(
        provider=provider,
        knowledge_storage=knowledge_storage,
        storage=storage,
        note_storage=note_storage,
        notes_dir=notes_dir,
        knowledge_dir=knowledge_dir,
        index=index,
        index_path=index_path,
        clock=clock,
    ).compile(topic, notes)


compile_knowledge = compile_topic
build_knowledge = compile_topic
update_topic = compile_topic


__all__ = [
    "KnowledgeCompilationError",
    "KnowledgeCompilationResult",
    "KnowledgeCompiler",
    "KnowledgeService",
    "NoteInput",
    "NotesInput",
    "TopicKnowledgeCompiler",
    "build_knowledge",
    "compile_knowledge",
    "compile_topic",
    "update_topic",
]
