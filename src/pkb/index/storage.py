"""Safe JSON persistence for the local index."""

import json
import os
from pathlib import Path
import tempfile

from pydantic import ValidationError

from pkb.index.model import IndexFile


class IndexStorageError(RuntimeError):
    """Raised when the JSON index cannot be read or written safely."""


def read_index(index_path: str | Path) -> IndexFile:
    """Read and validate one UTF-8 JSON index."""

    path = Path(index_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IndexStorageError(f"Invalid JSON index: {path}") from exc

    try:
        return IndexFile.model_validate(payload)
    except ValidationError as exc:
        raise IndexStorageError(f"Invalid JSON index structure: {path}") from exc


def write_index(index_path: str | Path, index: IndexFile) -> Path:
    """Atomically write a validated index as indented UTF-8 JSON."""

    if not isinstance(index, IndexFile):
        raise TypeError("index must be an IndexFile")

    path = Path(index_path)
    payload = json.dumps(
        index.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError as exc:
        raise IndexStorageError(f"Could not write JSON index: {path}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
    return path


class IndexStorage:
    """Small path-bound facade for callers that prefer an object API."""

    def __init__(self, index_path: str | Path) -> None:
        self.index_path = Path(index_path)

    def read(self) -> IndexFile:
        return read_index(self.index_path)

    def write(self, index: IndexFile) -> Path:
        return write_index(self.index_path, index)


read_json_index = read_index
write_json_index = write_index
