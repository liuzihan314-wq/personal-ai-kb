"""Atomic file storage for user-scoped operation history."""

from pathlib import Path
import re

from pydantic import ValidationError

from pkb.history.model import HistoryRecord


_RECORD_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class HistoryStorageError(RuntimeError):
    """Raised when a history record cannot be safely read or written."""


class HistoryStore:
    """Append-only history records inside one user-scoped ``history`` dir.

    Each record is one JSON file and is created with exclusive ``x`` mode, so
    an existing record is never silently overwritten.  Listing is scoped to
    the directory passed at construction time; there is no shared fallback.
    """

    def __init__(self, history_dir: str | Path) -> None:
        self.history_dir = Path(history_dir)

    def _record_path(self, record_id: str) -> Path:
        if not _RECORD_ID_PATTERN.fullmatch(record_id):
            raise HistoryStorageError("历史记录 ID 无效")
        return self.history_dir / f"{record_id}.json"

    def append(self, record: HistoryRecord) -> Path:
        """Persist one record, failing instead of overwriting an existing id."""

        path = self._record_path(record.id)
        try:
            self.history_dir.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as handle:
                handle.write(record.model_dump_json(indent=2))
                handle.write("\n")
        except FileExistsError as error:
            raise HistoryStorageError("历史记录已存在，拒绝覆盖") from error
        except OSError as error:
            raise HistoryStorageError(
                f"历史记录写入失败：{error.strerror or error.__class__.__name__}"
            ) from error
        return path

    def list_records(self) -> list[HistoryRecord]:
        """Return all records in chronological order.

        A missing directory means no history yet.  Corrupt or invalid files
        are reported rather than silently ignored so missing history cannot be
        mistaken for an empty history.
        """

        if not self.history_dir.exists():
            return []
        records: list[HistoryRecord] = []
        for path in self.history_dir.glob("*.json"):
            try:
                records.append(HistoryRecord.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValidationError) as error:
                raise HistoryStorageError(f"历史记录损坏：{path.name}") from error
        records.sort(key=lambda record: (record.created_at, record.id))
        return records


__all__ = ["HistoryStorageError", "HistoryStore"]
