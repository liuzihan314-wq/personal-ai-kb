"""Markdown and YAML-frontmatter encoding for Topic Knowledge."""

import json
from collections.abc import Iterable
from typing import Any

from pkb.knowledge.model import KnowledgeSource, TopicKnowledge


class KnowledgeFormatError(ValueError):
    """Raised when a Topic Knowledge Markdown file is not valid V1 format."""


def _yaml_scalar(value: Any) -> str:
    """Encode one scalar as a YAML-compatible JSON-quoted value."""

    if value is None:
        return "null"
    return json.dumps(str(value), ensure_ascii=False)


def _list_field(key: str, values: Iterable[str]) -> list[str]:
    items = list(values)
    if not items:
        return [f"{key}: []"]
    return [f"{key}:", *[f"  - {_yaml_scalar(item)}" for item in items]]


def encode_frontmatter(knowledge: TopicKnowledge) -> str:
    """Return the complete YAML frontmatter block for ``knowledge``."""

    if not isinstance(knowledge, TopicKnowledge):
        raise TypeError("knowledge must be a TopicKnowledge")

    lines = [
        "---",
        f"topic: {_yaml_scalar(knowledge.topic)}",
        f"created_at: {_yaml_scalar(knowledge.created_at.isoformat())}",
        f"updated_at: {_yaml_scalar(knowledge.updated_at.isoformat())}",
        *_list_field("source_note_ids", knowledge.source_note_ids),
        *_list_field("source_references", knowledge.source_references),
        *_list_field("source_titles", (source.title for source in knowledge.sources)),
        *_list_field(
            "raw_document_ids",
            (source.raw_document_id for source in knowledge.sources),
        ),
        "---",
    ]
    return "\n".join(lines)


def _inline(value: str) -> str:
    """Keep source metadata on one readable Markdown line."""

    return " ".join(value.split()).replace("`", "\\`")


def render_knowledge(knowledge: TopicKnowledge) -> str:
    """Serialize one Topic Knowledge page as UTF-8 Markdown."""

    if not isinstance(knowledge, TopicKnowledge):
        raise TypeError("knowledge must be a TopicKnowledge")

    lines = [
        encode_frontmatter(knowledge),
        "",
        f"# {_inline(knowledge.topic)}",
        "",
        "## Current synthesis",
        "",
        knowledge.current_synthesis,
        "",
        "## Sources",
        "",
    ]
    for source in knowledge.sources:
        title = source.title or source.note_id
        lines.extend(
            [
                f"- Note ID: `{_inline(source.note_id)}`",
                f"  - Title: {_inline(title)}",
                f"  - Raw document ID: `{_inline(source.raw_document_id)}`",
                f"  - Reference: {_inline(source.reference)}",
            ]
        )
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
            raise KnowledgeFormatError(
                f"Invalid quoted frontmatter value: {value}"
            ) from exc
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
            raise KnowledgeFormatError(f"Invalid frontmatter line: {line}")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        if not key:
            raise KnowledgeFormatError("Frontmatter keys cannot be empty")
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
        if index < len(lines) and lines[index].startswith((" ", "\t")):
            raise KnowledgeFormatError(f"Invalid frontmatter list item: {lines[index]}")
        values[key] = items
    return values


def _split_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    normalized = markdown.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        raise KnowledgeFormatError("Knowledge must start with YAML frontmatter")
    closing = normalized.find("\n---\n", 4)
    if closing < 0:
        raise KnowledgeFormatError("Knowledge frontmatter is not closed")
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


def _string_list(frontmatter: dict[str, Any], key: str) -> list[str]:
    value = frontmatter.get(key)
    if not isinstance(value, list) or not value:
        raise KnowledgeFormatError(f"Frontmatter field {key!r} must be a non-empty list")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise KnowledgeFormatError(f"Frontmatter field {key!r} must contain strings")
    return [item.strip() for item in value]


def _optional_string_list(
    frontmatter: dict[str, Any],
    key: str,
    *,
    length: int,
    default: list[str],
) -> list[str]:
    value = frontmatter.get(key)
    if value is None:
        return default
    if not isinstance(value, list) or len(value) != length:
        raise KnowledgeFormatError(
            f"Frontmatter field {key!r} must contain {length} values"
        )
    if any(not isinstance(item, str) for item in value):
        raise KnowledgeFormatError(f"Frontmatter field {key!r} must contain strings")
    return [item.strip() for item in value]


def parse_knowledge(markdown: str) -> TopicKnowledge:
    """Parse a Topic Knowledge page written by :func:`render_knowledge`."""

    if not isinstance(markdown, str):
        raise KnowledgeFormatError("Knowledge Markdown must be text")

    frontmatter, body = _split_frontmatter(markdown)
    required = ("topic", "created_at", "updated_at")
    missing = [key for key in required if not frontmatter.get(key)]
    if missing:
        raise KnowledgeFormatError(
            f"Missing frontmatter fields: {', '.join(missing)}"
        )

    source_note_ids = _string_list(frontmatter, "source_note_ids")
    source_references = _string_list(frontmatter, "source_references")
    if len(source_note_ids) != len(source_references):
        raise KnowledgeFormatError(
            "source_note_ids and source_references must have the same length"
        )
    source_titles = _optional_string_list(
        frontmatter,
        "source_titles",
        length=len(source_note_ids),
        default=[""] * len(source_note_ids),
    )
    raw_document_ids = _optional_string_list(
        frontmatter,
        "raw_document_ids",
        length=len(source_note_ids),
        default=source_note_ids.copy(),
    )

    sections = _parse_sections(body)
    synthesis = sections.get("Current synthesis", "")
    if not synthesis or synthesis == "_None identified._":
        raise KnowledgeFormatError("Knowledge body is missing current synthesis")
    sources_body = sections.get("Sources", "")
    if not sources_body or sources_body == "_None identified._":
        raise KnowledgeFormatError("Knowledge body is missing sources")

    try:
        sources = [
            KnowledgeSource(
                note_id=note_id,
                title=title,
                raw_document_id=raw_document_id,
                reference=reference,
            )
            for note_id, title, raw_document_id, reference in zip(
                source_note_ids,
                source_titles,
                raw_document_ids,
                source_references,
                strict=True,
            )
        ]
        return TopicKnowledge(
            topic=str(frontmatter["topic"]),
            created_at=frontmatter["created_at"],
            updated_at=frontmatter["updated_at"],
            source_note_ids=source_note_ids,
            source_references=source_references,
            synthesis=synthesis,
            sources=sources,
        )
    except (TypeError, ValueError) as exc:
        raise KnowledgeFormatError("Invalid Topic Knowledge fields") from exc


serialize_knowledge = render_knowledge
deserialize_knowledge = parse_knowledge
decode_knowledge = parse_knowledge
encode_topic_frontmatter = encode_frontmatter
render_topic_knowledge = render_knowledge
parse_topic_knowledge = parse_knowledge


__all__ = [
    "KnowledgeFormatError",
    "decode_knowledge",
    "deserialize_knowledge",
    "encode_frontmatter",
    "encode_topic_frontmatter",
    "parse_knowledge",
    "parse_topic_knowledge",
    "render_knowledge",
    "render_topic_knowledge",
    "serialize_knowledge",
]
