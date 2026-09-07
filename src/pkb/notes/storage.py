"""Exclusive local storage for generated Notes."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

from pkb.notes.markdown import NoteFormatError, parse_note, render_note
from pkb.notes.model import Note


class NoteStorageError(RuntimeError):
    """Raised when a Note cannot be read or written safely."""


class NoteAlreadyExistsError(NoteStorageError):
    """Raised only by callers that explicitly request rejection on duplicates."""


@dataclass(frozen=True)
class NoteRecord:
    """A Note together with its persisted path and creation status."""

    note: Note
    path: Path
    created: bool

    @property
    def document_id(self) -> str:
        return self.note.document_id


_SAFE_DOCUMENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def _filename_for(document_id: str) -> str:
    if (
        _SAFE_DOCUMENT_ID.fullmatch(document_id)
        and document_id.upper() not in _WINDOWS_RESERVED
    ):
        return f"{document_id}.md"
    digest = sha256(document_id.encode("utf-8")).hexdigest()
    return f"document-{digest}.md"


class NoteStorage:
    """Store one Markdown file per source document without overwriting it."""

    def __init__(self, notes_dir: str | Path) -> None:
        self.notes_dir = Path(notes_dir)

    def path_for(self, document_id: str) -> Path:
        """Return the safe, stable path for one source document ID."""

        if not isinstance(document_id, str) or not document_id.strip():
            raise NoteStorageError("document_id must be a non-empty string")
        return self.notes_dir / _filename_for(document_id)

    def exists(self, document_id: str) -> bool:
        return self.path_for(document_id).is_file()

    def read(self, document_id: str) -> NoteRecord:
        """Read one existing Note and verify its traceability ID."""

        path = self.path_for(document_id)
        if not path.is_file():
            raise FileNotFoundError(path)
        try:
            note = parse_note(path.read_text(encoding="utf-8"))
        except (OSError, NoteFormatError) as exc:
            raise NoteStorageError(f"Invalid Note file: {path}") from exc
        if note.document_id != document_id:
            raise NoteStorageError(f"Note document_id does not match its path: {path}")
        return NoteRecord(note=note, path=path, created=False)

    def read_if_exists(self, document_id: str) -> NoteRecord | None:
        path = self.path_for(document_id)
        if not path.exists():
            return None
        return self.read(document_id)

    def write(self, note: Note) -> NoteRecord:
        """Create a Note file, returning the existing file on duplicates."""

        path = self.path_for(note.document_id)
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8", newline="") as handle:
                handle.write(render_note(note))
        except FileExistsError:
            return self.read(note.document_id)
        except OSError as exc:
            raise NoteStorageError(f"Could not write Note: {path}") from exc
        return NoteRecord(note=note, path=path, created=True)
