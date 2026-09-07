"""Build the local JSON index from persisted Markdown Notes."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pkb.index.keywords import clean_values, extract_keywords
from pkb.index.model import IndexEntry, IndexFile
from pkb.index.related import DEFAULT_RELATED_THRESHOLD, build_related_map
from pkb.index.storage import write_index
from pkb.notes.markdown import NoteFormatError, parse_note
from pkb.notes.model import Note


class IndexBuildError(ValueError):
    """Raised when the Notes input cannot produce a trustworthy index."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class IndexBuilder:
    """Scan Notes, derive index fields, and calculate symmetric relations."""

    def __init__(
        self,
        notes_dir: str | Path,
        index_path: str | Path | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        related_threshold: float = DEFAULT_RELATED_THRESHOLD,
    ) -> None:
        self.notes_dir = Path(notes_dir)
        self.index_path = Path(index_path) if index_path is not None else (
            self.notes_dir.parent / "index" / "index.json"
        )
        if not 0.0 <= related_threshold <= 1.0:
            raise ValueError("related threshold must be between 0 and 1")
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.related_threshold = related_threshold

    def _note_paths(self) -> list[Path]:
        if not self.notes_dir.exists():
            raise IndexBuildError(f"Notes directory does not exist: {self.notes_dir}")
        if not self.notes_dir.is_dir():
            raise IndexBuildError(f"Notes path is not a directory: {self.notes_dir}")
        return sorted(
            (path for path in self.notes_dir.rglob("*.md") if path.is_file()),
            key=lambda path: path.as_posix(),
        )

    def _read_notes(self) -> list[tuple[Path, Note]]:
        notes: list[tuple[Path, Note]] = []
        seen_ids: dict[str, Path] = {}
        for path in self._note_paths():
            try:
                markdown = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise IndexBuildError(f"Could not read Note as UTF-8: {path}") from exc
            try:
                note = parse_note(markdown)
            except NoteFormatError as exc:
                raise IndexBuildError(f"Invalid Note file {path}: {exc}") from exc
            previous = seen_ids.get(note.document_id)
            if previous is not None:
                raise IndexBuildError(
                    f"Duplicate document_id {note.document_id!r} in Notes: "
                    f"{previous} and {path}"
                )
            seen_ids[note.document_id] = path
            notes.append((path, note))
        return notes

    def build(self) -> IndexFile:
        """Build an index in memory without touching the output file."""

        parsed_notes = self._read_notes()
        entries = [
            IndexEntry(
                document_id=note.document_id,
                title=note.title,
                created_at=note.created_at,
                content_type=note.content_type,
                tags=clean_values(note.tags),
                keywords=extract_keywords(note),
                source_type=note.source_type,
                note_path=str(path),
                topic=None,
            )
            for path, note in parsed_notes
        ]
        related = build_related_map(entries, threshold=self.related_threshold)
        entries = [
            entry.model_copy(update={"related": related[entry.document_id]})
            for entry in entries
        ]
        return IndexFile(
            generated_at=_utc(self.clock()),
            notes_dir=str(self.notes_dir),
            entries=entries,
        )

    def rebuild(self) -> IndexFile:
        """Build first, then atomically replace the JSON index."""

        index = self.build()
        write_index(self.index_path, index)
        return index

    rebuild_index = rebuild


IndexService = IndexBuilder


def build_index(
    notes_dir: str | Path,
    *,
    clock: Callable[[], datetime] | None = None,
    related_threshold: float = DEFAULT_RELATED_THRESHOLD,
) -> IndexFile:
    """Build an index in memory from one Notes directory."""

    return IndexBuilder(
        notes_dir,
        clock=clock,
        related_threshold=related_threshold,
    ).build()


def rebuild_index(
    notes_dir: str | Path,
    index_path: str | Path | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
    related_threshold: float = DEFAULT_RELATED_THRESHOLD,
) -> IndexFile:
    """Rebuild and persist an index from one Notes directory."""

    return IndexBuilder(
        notes_dir,
        index_path,
        clock=clock,
        related_threshold=related_threshold,
    ).rebuild()
