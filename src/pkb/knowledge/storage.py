"""Safe local Markdown storage for compiled Topic Knowledge."""

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import os
from pathlib import Path
import re
import tempfile
import unicodedata

from pkb.knowledge.markdown import KnowledgeFormatError, parse_knowledge, render_knowledge
from pkb.knowledge.model import KnowledgeSource, TopicKnowledge


class KnowledgeStorageError(RuntimeError):
    """Raised when a Topic Knowledge file cannot be read or written safely."""


class KnowledgeTopicConflictError(KnowledgeStorageError):
    """Raised when a destination already belongs to a different topic."""


@dataclass(frozen=True)
class KnowledgeRecord:
    """A persisted Topic Knowledge page and whether this call created it."""

    knowledge: TopicKnowledge
    path: Path
    created: bool

    @property
    def topic(self) -> str:
        return self.knowledge.topic

    @property
    def source_note_ids(self) -> list[str]:
        return self.knowledge.source_note_ids

    @property
    def source_references(self) -> list[str]:
        return self.knowledge.source_references

    @property
    def source_refs(self) -> list[str]:
        return self.knowledge.source_references
    @property
    def created_at(self) -> datetime:
        return self.knowledge.created_at

    @property
    def updated_at(self) -> datetime:
        return self.knowledge.updated_at

    @property
    def synthesis(self) -> str:
        return self.knowledge.current_synthesis

    @property
    def current_synthesis(self) -> str:
        return self.knowledge.current_synthesis

    @property
    def current_judgment(self) -> str:
        return self.knowledge.current_synthesis

    @property
    def sources(self) -> list[KnowledgeSource]:
        return self.knowledge.sources

    @property
    def updated(self) -> bool:
        return not self.created


def normalize_topic(topic: str) -> str:
    """Normalize whitespace while preserving the user's topic spelling."""

    if not isinstance(topic, str):
        raise KnowledgeStorageError("topic must be a non-empty string")
    normalized = " ".join(topic.split())
    if not normalized:
        raise KnowledgeStorageError("topic must be a non-empty string")
    return normalized


def topic_identity(topic: str) -> str:
    """Return the cross-platform identity used to locate a topic file."""

    return normalize_topic(topic)


def _slug(topic: str) -> str:
    ascii_topic = unicodedata.normalize("NFKD", topic).encode(
        "ascii", "ignore"
    ).decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "-", ascii_topic).strip("-").lower()
    return value[:48] or "topic"


def _filename_for(topic: str) -> str:
    normalized = normalize_topic(topic)
    digest = sha256(topic_identity(normalized).encode("utf-8")).hexdigest()
    return f"topic-{_slug(normalized)}-{digest}.md"


class KnowledgeStorage:
    """Store one safe, stable Markdown file per topic."""

    def __init__(self, knowledge_dir: str | Path) -> None:
        self.knowledge_dir = Path(knowledge_dir)

    def path_for(self, topic: str) -> Path:
        """Return the deterministic, cross-platform path for ``topic``."""

        return self.knowledge_dir / _filename_for(topic)

    def exists(self, topic: str) -> bool:
        return self.path_for(topic).is_file()

    def _read_path(self, path: Path) -> TopicKnowledge:
        try:
            markdown = path.read_text(encoding="utf-8")
            knowledge = parse_knowledge(markdown)
        except FileNotFoundError:
            raise
        except (OSError, UnicodeError, KnowledgeFormatError) as exc:
            raise KnowledgeStorageError(f"Invalid Knowledge file: {path}") from exc
        return knowledge

    def read(self, topic_or_path: str | Path) -> TopicKnowledge:
        """Read and validate a topic by name or an explicit Markdown path."""

        if isinstance(topic_or_path, Path):
            path = topic_or_path
            expected_topic: str | None = None
        elif isinstance(topic_or_path, str):
            possible_path = Path(topic_or_path)
            if possible_path.is_file():
                path = possible_path
                expected_topic = None
            else:
                path = self.path_for(topic_or_path)
                expected_topic = normalize_topic(topic_or_path)
        else:
            raise KnowledgeStorageError("topic_or_path must be a topic or Path")

        if not path.is_file():
            raise FileNotFoundError(path)
        knowledge = self._read_path(path)
        if (
            expected_topic is not None
            and topic_identity(knowledge.topic) != topic_identity(expected_topic)
        ):
            raise KnowledgeTopicConflictError(
                f"Knowledge file does not belong to topic {expected_topic!r}: {path}"
            )
        return knowledge

    def read_if_exists(self, topic: str) -> KnowledgeRecord | None:
        path = self.path_for(topic)
        if not path.exists():
            return None
        knowledge = self.read(topic)
        return KnowledgeRecord(knowledge=knowledge, path=path, created=False)

    def write(self, knowledge: TopicKnowledge) -> KnowledgeRecord:
        """Atomically create or replace one topic page after conflict checks."""

        if not isinstance(knowledge, TopicKnowledge):
            raise TypeError("knowledge must be a TopicKnowledge")

        path = self.path_for(knowledge.topic)
        existed = path.exists()
        if existed:
            if not path.is_file():
                raise KnowledgeStorageError(
                    f"Knowledge destination is not a file: {path}"
                )
            existing = self.read(knowledge.topic)
            if topic_identity(existing.topic) != topic_identity(knowledge.topic):
                raise KnowledgeTopicConflictError(
                    f"Knowledge destination belongs to another topic: {path}"
                )

        payload = render_knowledge(knowledge)
        temporary_path: Path | None = None
        try:
            self.knowledge_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=self.knowledge_dir,
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
            raise KnowledgeStorageError(f"Could not write Knowledge: {path}") from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
        return KnowledgeRecord(knowledge=knowledge, path=path, created=not existed)

    save = write
    store = write
    read_topic = read
    write_topic = write


def read_knowledge(
    knowledge_dir: str | Path,
    topic_or_path: str | Path | None = None,
) -> TopicKnowledge:
    """Read one Knowledge page through a path-bound storage facade."""

    if topic_or_path is None:
        path = Path(knowledge_dir)
        if not path.is_file():
            raise FileNotFoundError(path)
        return KnowledgeStorage(path.parent).read(path)
    return KnowledgeStorage(knowledge_dir).read(topic_or_path)


def write_knowledge(
    knowledge_dir: str | Path,
    knowledge: TopicKnowledge,
) -> KnowledgeRecord:
    """Write one Knowledge page through a path-bound storage facade."""

    return KnowledgeStorage(knowledge_dir).write(knowledge)


KnowledgeConflictError = KnowledgeTopicConflictError


__all__ = [
    "KnowledgeConflictError",
    "KnowledgeRecord",
    "KnowledgeStorage",
    "KnowledgeStorageError",
    "KnowledgeTopicConflictError",
    "normalize_topic",
    "read_knowledge",
    "topic_identity",
    "write_knowledge",
]
