"""Safe, read-only observations for the WeChat macOS feasibility POC.

The observer records only filesystem metadata and whether a file has a
standard SQLite header / can be opened in SQLite read-only mode.  It never
queries rows, copies data, decrypts files, or writes a result.
"""

from dataclasses import dataclass
import sqlite3
from pathlib import Path
from urllib.parse import quote


_SQLITE_HEADER = b"SQLite format 3\x00"


@dataclass(frozen=True)
class DatabaseObservation:
    """Non-content facts about one candidate database file."""

    exists: bool
    size_bytes: int | None
    modified_ns: int | None
    has_sqlite_header: bool
    sqlite_readable: bool
    error_kind: str | None


def observe_database(path: Path) -> DatabaseObservation:
    """Observe one path without retaining its name or reading any rows.

    ``error_kind`` is intentionally coarse so an exception cannot leak a
    path, query, or database content into a report or log.
    """

    try:
        stat = path.stat()
    except FileNotFoundError:
        return DatabaseObservation(False, None, None, False, False, "missing")
    except OSError:
        return DatabaseObservation(False, None, None, False, False, "stat_error")

    try:
        with path.open("rb") as handle:
            has_sqlite_header = handle.read(len(_SQLITE_HEADER)) == _SQLITE_HEADER
    except OSError:
        return DatabaseObservation(
            True,
            stat.st_size,
            stat.st_mtime_ns,
            False,
            False,
            "read_error",
        )

    if not has_sqlite_header:
        return DatabaseObservation(
            True,
            stat.st_size,
            stat.st_mtime_ns,
            False,
            False,
            "missing_sqlite_header",
        )

    try:
        uri = f"file:{quote(str(path.resolve()))}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            connection.execute("PRAGMA schema_version").fetchone()
        finally:
            connection.close()
    except (OSError, sqlite3.Error):
        return DatabaseObservation(
            True,
            stat.st_size,
            stat.st_mtime_ns,
            True,
            False,
            "sqlite_read_error",
        )

    return DatabaseObservation(
        True,
        stat.st_size,
        stat.st_mtime_ns,
        True,
        True,
        None,
    )
