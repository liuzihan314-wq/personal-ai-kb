"""Immutable, file-based storage for imported source material."""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from pkb.models import UnifiedDocument


class RawStorageError(RuntimeError):
    """Raised when an immutable Raw record cannot be safely written."""


@dataclass(frozen=True)
class RawPaths:
    """Paths for the files belonging to one Raw document record."""

    directory: Path
    original_file: Path
    extracted_text_file: Path
    metadata_file: Path


class RawStorage:
    """Store one source document, its text, and readable metadata per record.

    The document id is derived by the importer from the source bytes.  A
    complete record is therefore also the deduplication index, without a
    database or a mutable catalog.  All final files are opened exclusively so
    an existing Raw file can never be overwritten.
    """

    def __init__(self, raw_dir: str | Path) -> None:
        self.raw_dir = Path(raw_dir)

    def paths_for(
        self,
        document_id: str,
        *,
        content_type: str | None = None,
    ) -> RawPaths:
        """Return the stable Raw paths for a document id.

        PDFs keep the original V1 paths.  Manual idea cards and WeChat
        articles have no binary source file, so their UTF-8 source text is
        stored as ``original.txt`` and is also the extracted-text view.
        """

        directory = self.raw_dir / document_id
        if content_type in {"idea", "article"} or (
            content_type is None
            and not (directory / "original.pdf").is_file()
            and (directory / "original.txt").is_file()
        ):
            original_file = directory / "original.txt"
            extracted_text_file = original_file
        else:
            original_file = directory / "original.pdf"
            extracted_text_file = directory / "extracted.txt"

        return RawPaths(
            directory=directory,
            original_file=original_file,
            extracted_text_file=extracted_text_file,
            metadata_file=directory / "metadata.json",
        )

    def has_document(self, document_id: str) -> bool:
        """Return whether a complete immutable Raw record exists."""

        paths = self.paths_for(document_id)
        return all(
            path.is_file()
            for path in {
                paths.original_file,
                paths.extracted_text_file,
                paths.metadata_file,
            }
        )

    def store(self, document: UnifiedDocument, original_bytes: bytes) -> UnifiedDocument:
        """Write a new Raw record or return the already stored duplicate.

        A pre-existing incomplete record is treated as an error instead of
        being repaired, because repairing it could overwrite or reinterpret
        an immutable source record.
        """

        paths = self.paths_for(document.id, content_type=document.content_type)
        if self.has_document(document.id):
            return self.load_document(document.id)
        if paths.directory.exists():
            raise RawStorageError(
                f"Raw record is incomplete and cannot be overwritten: {paths.directory}"
            )

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        try:
            paths.directory.mkdir()
        except FileExistsError:
            if self.has_document(document.id):
                return self.load_document(document.id)
            raise RawStorageError(
                f"Raw record is incomplete and cannot be overwritten: {paths.directory}"
            )

        self._write_bytes_exclusive(paths.original_file, original_bytes)
        if paths.extracted_text_file != paths.original_file:
            self._write_text_exclusive(paths.extracted_text_file, document.content)
        self._write_metadata_exclusive(paths.metadata_file, document)
        return document

    def read_metadata(self, document_id: str) -> dict[str, Any]:
        """Read the human-readable metadata file for a stored document."""

        paths = self.paths_for(document_id)
        if not paths.metadata_file.is_file():
            raise FileNotFoundError(paths.metadata_file)
        payload = json.loads(paths.metadata_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RawStorageError(f"Invalid Raw metadata: {paths.metadata_file}")
        return payload

    def load_document(self, document_id: str) -> UnifiedDocument:
        """Reconstruct a document from its immutable metadata and text files."""

        if not self.has_document(document_id):
            raise FileNotFoundError(self.paths_for(document_id).directory)

        payload = self.read_metadata(document_id)
        payload["content"] = self.paths_for(document_id).extracted_text_file.read_text(
            encoding="utf-8"
        )
        return UnifiedDocument.model_validate(payload)

    @staticmethod
    def _write_bytes_exclusive(path: Path, content: bytes) -> None:
        with path.open("xb") as handle:
            handle.write(content)

    @staticmethod
    def _write_text_exclusive(path: Path, content: str) -> None:
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(content)

    @staticmethod
    def _write_metadata_exclusive(path: Path, document: UnifiedDocument) -> None:
        payload = document.model_dump(mode="json", exclude={"content"})
        with path.open("x", encoding="utf-8", newline="") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
