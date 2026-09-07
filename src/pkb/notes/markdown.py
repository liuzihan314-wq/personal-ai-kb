"""Markdown and YAML-frontmatter encoding for Notes.

The project intentionally has no YAML runtime dependency in V1.  The
frontmatter writer emits a small, valid YAML subset using JSON-quoted scalar
values; the reader accepts that subset and is only responsible for files
written by this package.
"""

import json
from collections.abc import Iterable
from typing import Any

from pkb.notes.model import Note


class NoteFormatError(ValueError):
    """Raised when a persisted Note is not in the supported format."""


def _yaml_scalar(value: Any) -> str:
    """Encode one scalar as a YAML-compatible JSON-quoted value."""

    if value is None:
        return "null"
    return json.dumps(str(value), ensure_ascii=False)


def encode_frontmatter(note: Note) -> str:
    """Return the complete YAML frontmatter block for ``note``."""

    fields: list[tuple[str, Any]] = [
        ("document_id", note.document_id),
        ("source_type", note.source_type),
        ("title", note.title),
        ("created_at", note.created_at.isoformat()),
        ("tags", note.tags),
        ("content_type", note.content_type or None),
        ("source_url", note.source_url),
        ("original_file", note.original_file),
        ("source_reference", note.source_reference or None),
        ("user_note", note.user_note),
    ]

    lines = ["---"]
    for key, value in fields:
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                lines.extend(f"  - {_yaml_scalar(item)}" for item in value)
        elif value is not None:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def _section(title: str, content: str) -> list[str]:
    """Render one body section while keeping an empty section readable."""

    return [f"## {title}", "", content.strip() or "_None identified._", ""]


def _bullet_section(title: str, values: Iterable[str]) -> list[str]:
    items = [value.strip() for value in values if value.strip()]
    lines = [f"## {title}", ""]
    lines.extend(f"- {item}" for item in items)
    if not items:
        lines.append("_None identified._")
    lines.append("")
    return lines


def _quote_section(values: Iterable[str]) -> list[str]:
    items = [value.strip() for value in values if value.strip()]
    lines = ["## Quotes", ""]
    for index, quote in enumerate(items):
        if index:
            lines.append("")
        lines.extend(f"> {line}" if line else ">" for line in quote.splitlines())
    if not items:
        lines.append("_None identified._")
    lines.append("")
    return lines


def render_note(note: Note) -> str:
    """Serialize one Note as UTF-8 Markdown with YAML frontmatter."""

    heading = " ".join(note.title.split())
    lines = [encode_frontmatter(note), "", f"# {heading}", ""]
    if note.content_type == "idea" and note.original_content:
        lines.extend(_section("Original idea", note.original_content))
    lines.extend(_section("Summary", note.summary))
    lines.extend(_bullet_section("Key points", note.key_points))
    lines.extend(_quote_section(note.quotes))
    if note.user_note:
        lines.extend(_section("Personal note", note.user_note))

    lines.extend(
        [
            "## Source",
            "",
            f"- Document ID: `{note.document_id}`",
            f"- Source type: `{note.source_type}`",
            f"- Reference: {note.source_reference or f'raw:{note.document_id}'}",
        ]
    )
    if note.source_url:
        lines.append(f"- URL: {note.source_url}")
    if note.original_file:
        lines.append(f"- Original file: `{note.original_file}`")
    return "\n".join(lines).rstrip() + "\n"


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "null":
        return None
    if value == "[]":
        return []
    if value.startswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise NoteFormatError(f"Invalid quoted frontmatter value: {value}") from exc
    return value


def _parse_frontmatter(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    values: dict[str, Any] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith((" ", "\t")) or ":" not in line:
            raise NoteFormatError(f"Invalid frontmatter line: {line}")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        if not key:
            raise NoteFormatError("Frontmatter keys cannot be empty")
        raw_value = raw_value.strip()
        if raw_value:
            values[key] = _parse_scalar(raw_value)
            index += 1
            continue

        items: list[Any] = []
        index += 1
        while index < len(lines) and lines[index].startswith("  - "):
            items.append(_parse_scalar(lines[index][4:]))
            index += 1
        values[key] = items
    return values


def _split_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    normalized = markdown.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        raise NoteFormatError("Note must start with YAML frontmatter")
    closing = normalized.find("\n---\n", 4)
    if closing < 0:
        raise NoteFormatError("Note frontmatter is not closed")
    frontmatter = normalized[4:closing]
    body = normalized[closing + len("\n---\n") :]
    return _parse_frontmatter(frontmatter), body


def _parse_sections(body: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {title: "\n".join(lines).strip() for title, lines in sections.items()}


def _parse_bullets(section: str | None) -> list[str]:
    if not section or section == "_None identified._":
        return []
    return [line[2:].strip() for line in section.splitlines() if line.startswith("- ")]


def _parse_quotes(section: str | None) -> list[str]:
    if not section or section == "_None identified._":
        return []
    quotes: list[str] = []
    current: list[str] = []
    for line in section.splitlines():
        if line == ">" or line.startswith("> "):
            current.append(line[1:].lstrip())
        elif current:
            quotes.append("\n".join(current).strip())
            current = []
    if current:
        quotes.append("\n".join(current).strip())
    return [quote for quote in quotes if quote]


def parse_note(markdown: str) -> Note:
    """Parse a Note written by :func:`render_note`."""

    frontmatter, body = _split_frontmatter(markdown)
    sections = _parse_sections(body)
    required = ("document_id", "source_type", "title", "created_at")
    missing = [key for key in required if not frontmatter.get(key)]
    if missing:
        raise NoteFormatError(f"Missing frontmatter fields: {', '.join(missing)}")
    summary = sections.get("Summary", "")
    if not summary or summary == "_None identified._":
        raise NoteFormatError("Note body is missing a summary")

    try:
        return Note(
            document_id=str(frontmatter["document_id"]),
            source_type=str(frontmatter["source_type"]),
            title=str(frontmatter["title"]),
            created_at=frontmatter["created_at"],
            tags=[str(value) for value in (frontmatter.get("tags") or [])],
            summary=summary,
            key_points=_parse_bullets(sections.get("Key points")),
            quotes=_parse_quotes(sections.get("Quotes")),
            content_type=str(frontmatter.get("content_type") or ""),
            source_url=(
                str(frontmatter["source_url"])
                if frontmatter.get("source_url") is not None
                else None
            ),
            original_file=(
                str(frontmatter["original_file"])
                if frontmatter.get("original_file") is not None
                else None
            ),
            source_reference=str(frontmatter.get("source_reference") or ""),
            original_content=sections.get("Original idea") or None,
            user_note=(
                sections.get("Personal note")
                or (str(frontmatter["user_note"]) if frontmatter.get("user_note") else None)
            ),
        )
    except (TypeError, ValueError) as exc:
        raise NoteFormatError("Invalid Note fields") from exc


# Names that read naturally for callers and keep the format module discoverable.
serialize_note = render_note
deserialize_note = parse_note
decode_note = parse_note
