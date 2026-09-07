"""Single-document AI Notes and their local Markdown storage."""

from pkb.notes.markdown import (
    NoteFormatError,
    decode_note,
    deserialize_note,
    encode_frontmatter,
    parse_note,
    render_note,
    serialize_note,
)
from pkb.notes.model import Note
from pkb.notes.service import (
    NoteGenerationError,
    NoteGenerationResult,
    NoteGenerator,
    NoteService,
    SingleDocumentNoteService,
    generate_note,
)
from pkb.notes.storage import (
    NoteAlreadyExistsError,
    NoteRecord,
    NoteStorage,
    NoteStorageError,
)

__all__ = [
    "Note",
    "NoteAlreadyExistsError",
    "NoteFormatError",
    "NoteGenerationError",
    "NoteGenerationResult",
    "NoteGenerator",
    "NoteRecord",
    "NoteService",
    "NoteStorage",
    "NoteStorageError",
    "SingleDocumentNoteService",
    "decode_note",
    "deserialize_note",
    "encode_frontmatter",
    "generate_note",
    "parse_note",
    "render_note",
    "serialize_note",
]
