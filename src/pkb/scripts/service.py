"""Local, traceable spoken-script generation after topic selection.

The writer deliberately keeps the V1 flow explicit:

``selected topic -> local Retrieval -> readable evidence -> script``

It never writes Raw, Notes, Knowledge, or Index data. Drafts must come from a
configured provider and pass the copy gate; rejected drafts are never replaced
with a template assembled from article summaries.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import re
from typing import TypeAlias

from pkb.config import get_settings
from pkb.index.model import IndexFile
from pkb.index.storage import IndexStorageError, read_index
from pkb.knowledge.markdown import KnowledgeFormatError, parse_knowledge
from pkb.knowledge.model import TopicKnowledge
from pkb.knowledge.storage import KnowledgeRecord
from pkb.notes.markdown import NoteFormatError, parse_note
from pkb.notes.model import Note
from pkb.notes.storage import NoteRecord, NoteStorage, NoteStorageError
from pkb.providers import AIProvider, ProviderDocument, configured_provider
from pkb.providers.protocol import VisualMaterialSuggestion
from pkb.retrieval.model import RetrievalCandidate, RetrievalResult
from pkb.retrieval.service import RetrievalService, parse_query
from pkb.storage import RawStorage, RawStorageError
from pkb.topics.model import TopicCandidate

from pkb.scripts.model import (
    ScriptEvidence,
    ScriptResult,
    ScriptSelection,
    ScriptSource,
)


class ScriptGenerationError(ValueError):
    """Base error for invalid local script-generation inputs."""


class ScriptInputError(ScriptGenerationError):
    """Raised when the selected topic or service configuration is invalid."""


class ScriptStorageError(ScriptGenerationError):
    """Raised when local evidence cannot be read or validated safely."""


class ScriptProviderError(ScriptGenerationError):
    """Raised when the configured provider cannot write a script."""


class ScriptQualityError(ScriptGenerationError):
    """Two drafting attempts failed the publishable-copy gate."""


IndexInput: TypeAlias = IndexFile | str | Path
NoteInput: TypeAlias = Note | NoteRecord | str | Path
KnowledgeInput: TypeAlias = TopicKnowledge | KnowledgeRecord | str | Path
SelectionInput: TypeAlias = TopicCandidate | ScriptSelection | str

DEFAULT_LIMIT = 10
MIN_SCRIPT_CHARS = 650
MAX_SCRIPT_CHARS = 900
TARGET_SECONDS = 180
FORBIDDEN_SCRIPT_MARKERS = (
    "来源一",
    "来源二",
    "来源三",
    "来源 1",
    "来源 2",
    "来源 3",
    "Raw",
    "Note",
    "Knowledge",
    "本地 Index",
    "本地检索",
    "根据资料",
    "根据文档",
    "原始文章",
    "原始内容",
    "本地来源",
    "当前综合",
    "来源链",
    "二次检索",
    "可读取",
)

_SCRIPT_MARKER_REPLACEMENTS = {
    "来源一": "这部分内容",
    "来源二": "这部分内容",
    "来源三": "这部分内容",
    "来源 1": "这部分内容",
    "来源 2": "这部分内容",
    "来源 3": "这部分内容",
    "本地 Index": "检索结果",
    "本地检索": "检索结果",
    "根据资料": "结合已知内容",
    "根据文档": "结合已知内容",
    "原始文章": "这件事",
    "原始内容": "具体内容",
    "本地来源": "现有内容",
    "当前综合": "核心结论",
    "来源链": "相关内容",
    "二次检索": "再次梳理",
    "可读取": "能确认",
}


@dataclass(frozen=True)
class _LoadedKnowledge:
    knowledge: TopicKnowledge
    path: Path


@dataclass(frozen=True)
class _ResolvedNote:
    document_id: str
    raw_document_id: str
    note: Note | None
    path: Path
    title: str
    reference: str


@dataclass(frozen=True)
class _RawMaterial:
    document_id: str
    title: str
    content: str
    original_path: Path
    extracted_path: Path


def _excerpt(value: str, *, limit: int = 180) -> str:
    """Normalize and cap one piece of local evidence for writing context."""

    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _clean(value: str) -> str:
    return " ".join(value.split()).strip()


def _topic_key(value: str) -> str:
    return _clean(value).casefold()


def _as_sequence(value: object) -> list[object]:
    if isinstance(value, (str, Path)):
        return [value]
    if isinstance(value, Sequence):
        return list(value)
    try:
        return list(iter(value))  # type: ignore[arg-type]
    except TypeError as exc:
        raise ScriptInputError("input must be a model, path, or sequence") from exc


def _note_files(path: Path) -> list[Path]:
    if not path.exists():
        raise ScriptStorageError(f"Notes path does not exist: {path}")
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise ScriptStorageError(f"Notes path is not a directory: {path}")
    return sorted(
        (item for item in path.rglob("*.md") if item.is_file()),
        key=lambda item: item.as_posix(),
    )


def _knowledge_files(path: Path) -> list[Path]:
    if not path.exists():
        raise ScriptStorageError(f"Knowledge path does not exist: {path}")
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise ScriptStorageError(f"Knowledge path is not a directory: {path}")
    return sorted(
        (item for item in path.rglob("*.md") if item.is_file()),
        key=lambda item: item.as_posix(),
    )


def _read_note(path: Path) -> Note:
    try:
        return parse_note(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, NoteFormatError) as exc:
        raise ScriptStorageError(f"Invalid Note file: {path}") from exc


def _read_knowledge(path: Path) -> TopicKnowledge:
    try:
        return parse_knowledge(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, KnowledgeFormatError) as exc:
        raise ScriptStorageError(f"Invalid Knowledge file: {path}") from exc


def _load_notes(value: object | None) -> dict[str, NoteRecord]:
    """Load supplied Notes without writing or changing their representation."""

    if value is None:
        return {}

    loaded: dict[str, NoteRecord] = {}
    for item in _as_sequence(value):
        if isinstance(item, NoteRecord):
            records = [item]
        elif isinstance(item, Note):
            records = [
                NoteRecord(
                    note=item,
                    path=Path(f"note:{item.document_id}"),
                    created=False,
                )
            ]
        elif isinstance(item, (str, Path)):
            records = [
                NoteRecord(note=_read_note(path), path=path, created=False)
                for path in _note_files(Path(item))
            ]
        else:
            raise ScriptInputError(f"Unsupported Notes input: {type(item).__name__}")

        for record in records:
            document_id = record.note.document_id
            previous = loaded.get(document_id)
            if previous is not None and previous.path != record.path:
                raise ScriptInputError(f"Duplicate source Note ID: {document_id}")
            loaded[document_id] = record
    return loaded


def _load_knowledge(value: object | None) -> list[_LoadedKnowledge]:
    """Load supplied Topic Knowledge pages in stable path order."""

    if value is None:
        return []

    loaded: list[_LoadedKnowledge] = []
    seen_topics: set[str] = set()
    for item in _as_sequence(value):
        if isinstance(item, KnowledgeRecord):
            records = [_LoadedKnowledge(item.knowledge, item.path)]
        elif isinstance(item, TopicKnowledge):
            records = [
                _LoadedKnowledge(
                    item,
                    Path(f"knowledge:{item.topic}"),
                )
            ]
        elif isinstance(item, (str, Path)):
            records = [
                _LoadedKnowledge(_read_knowledge(path), path)
                for path in _knowledge_files(Path(item))
            ]
        else:
            raise ScriptInputError(
                f"Unsupported Knowledge input: {type(item).__name__}"
            )

        for record in records:
            key = _topic_key(record.knowledge.topic)
            if key in seen_topics:
                raise ScriptInputError(
                    f"Duplicate Topic Knowledge topic: {record.knowledge.topic}"
                )
            seen_topics.add(key)
            loaded.append(record)
    return loaded


def _candidate_path(
    candidate: RetrievalCandidate,
    index: IndexFile,
    *,
    index_path: Path | None,
    notes_dir: Path,
) -> Path:
    """Resolve an Index path using the same relative-path fallbacks as Q&A."""

    raw_path = Path(candidate.note_path)
    options: list[Path] = [raw_path]
    if not raw_path.is_absolute() and index_path is not None:
        options.append(index_path.parent / raw_path)
    if not raw_path.is_absolute():
        options.extend(
            [
                notes_dir / raw_path.name,
                notes_dir / raw_path,
                Path(index.notes_dir) / raw_path.name,
                Path(index.notes_dir) / raw_path,
            ]
        )
    seen: set[Path] = set()
    for option in options:
        if option in seen:
            continue
        seen.add(option)
        if option.is_file():
            return option
    return options[0]


def _read_candidate_note(path: Path, document_id: str) -> NoteRecord | None:
    if not path.is_file():
        return None
    note = _read_note(path)
    if note.document_id != document_id:
        raise ScriptStorageError(f"Note ID does not match its path: {path}")
    return NoteRecord(note=note, path=path, created=False)


def _raw_id_from_reference(reference: str, fallback: str) -> str:
    cleaned = _clean(reference)
    if cleaned.startswith("raw:") and cleaned[4:].strip():
        return cleaned[4:].strip()
    return fallback


def _provider_note(note: Note) -> ProviderDocument:
    sections = [f"Title: {note.title}", f"Summary: {note.summary}"]
    if note.key_points:
        sections.append("Key points:\n" + "\n".join(f"- {item}" for item in note.key_points))
    if note.quotes:
        sections.append("Quotes:\n" + "\n".join(f'- "{item}"' for item in note.quotes))
    if note.original_content:
        sections.append(f"Original idea:\n{note.original_content}")
    if note.user_note:
        sections.append(f"Personal note:\n{note.user_note}")
    return ProviderDocument(
        document_id=note.document_id,
        title=note.title,
        content="\n\n".join(sections),
        source=note.source_reference or f"raw:{note.document_id}",
    )


def _provider_knowledge(record: _LoadedKnowledge) -> ProviderDocument:
    knowledge = record.knowledge
    source_lines = [
        f"- {source.note_id}: {source.title or source.reference}"
        for source in knowledge.sources
    ]
    content = (
        f"Topic: {knowledge.topic}\n"
        f"Current synthesis:\n{knowledge.current_synthesis}\n"
        "Knowledge source Notes:\n"
        + "\n".join(source_lines)
    )
    return ProviderDocument(
        document_id=f"knowledge:{knowledge.topic}",
        title=knowledge.topic,
        content=content,
        source=str(record.path),
    )


def _provider_raw(material: _RawMaterial) -> ProviderDocument:
    return ProviderDocument(
        document_id=material.document_id,
        title=material.title,
        content=material.content,
        source=str(material.extracted_path),
    )


class _ScriptWriterCore:
    """Write one spoken script from a confirmed topic and fresh local evidence."""

    def __init__(
        self,
        index: IndexInput | None = None,
        *,
        index_path: str | Path | None = None,
        knowledge: KnowledgeInput | Sequence[KnowledgeInput] | None = None,
        knowledge_dir: str | Path | None = None,
        notes: NoteInput | Sequence[NoteInput] | None = None,
        notes_dir: str | Path | None = None,
        raw_dir: str | Path | None = None,
        raw_storage: RawStorage | None = None,
        retrieval: RetrievalService | None = None,
        retrieval_service: RetrievalService | None = None,
        provider: AIProvider | None = None,
    ) -> None:
        settings = get_settings()
        if index is not None and index_path is not None:
            raise ScriptInputError("Pass index or index_path, not both")
        if knowledge is not None and knowledge_dir is not None:
            raise ScriptInputError("Pass knowledge or knowledge_dir, not both")
        if notes is not None and notes_dir is not None:
            raise ScriptInputError("Pass notes or notes_dir, not both")
        if retrieval is not None and retrieval_service is not None:
            raise ScriptInputError("Pass retrieval or retrieval_service, not both")
        if raw_dir is not None and raw_storage is not None:
            raise ScriptInputError("Pass raw_dir or raw_storage, not both")

        if isinstance(index, IndexFile):
            self._index = index
            self.index_path: Path | None = None
        else:
            self._index = None
            self.index_path = Path(
                index if index is not None else index_path or settings.index_dir / "index.json"
            )

        self.knowledge_input = knowledge
        self.knowledge_dir = Path(
            knowledge_dir if knowledge_dir is not None else settings.knowledge_dir
        )
        self.notes_input = notes
        self.notes_dir = Path(notes_dir if notes_dir is not None else settings.notes_dir)
        self.raw_storage = raw_storage or RawStorage(
            raw_dir if raw_dir is not None else settings.raw_dir
        )
        self.retrieval_service = retrieval or retrieval_service
        if self.retrieval_service is None:
            self.retrieval_service = (
                RetrievalService(index=self._index)
                if self._index is not None
                else RetrievalService(index_path=self.index_path)
            )
        self.provider = provider or configured_provider(get_settings())

    def _load_index(self) -> IndexFile:
        if self._index is not None:
            return self._index
        assert self.index_path is not None
        try:
            return read_index(self.index_path)
        except FileNotFoundError as exc:
            raise ScriptStorageError(f"JSON Index does not exist: {self.index_path}") from exc
        except IndexStorageError as exc:
            raise ScriptStorageError(f"Invalid JSON Index: {self.index_path}") from exc

    def _load_notes(self, selection: ScriptSelection) -> dict[str, NoteRecord]:
        if self.notes_input is not None:
            loaded = _load_notes(self.notes_input)
        elif self.notes_dir.exists():
            loaded = _load_notes(self.notes_dir)
        else:
            loaded = {}

        # A selected TopicCandidate may carry a concrete Note path from a
        # previous topic-generation call.  It is only a loading hint; the
        # current Retrieval result still decides which Notes are used.
        candidate = selection.candidate
        if candidate is not None:
            for source in candidate.sources:
                if source.kind != "note":
                    continue
                path = Path(source.path)
                if not path.is_file():
                    continue
                record = NoteRecord(note=_read_note(path), path=path, created=False)
                previous = loaded.get(record.note.document_id)
                if previous is not None and previous.path != record.path:
                    continue
                loaded[record.note.document_id] = record
        return loaded

    def _load_knowledge(self, selection: ScriptSelection) -> list[_LoadedKnowledge]:
        if self.knowledge_input is not None:
            loaded = _load_knowledge(self.knowledge_input)
        elif self.knowledge_dir.exists():
            loaded = _load_knowledge(self.knowledge_dir)
        else:
            loaded = []

        candidate = selection.candidate
        if candidate is None:
            return loaded

        known_topics = {_topic_key(item.knowledge.topic) for item in loaded}
        for source in candidate.sources:
            if source.kind != "knowledge":
                continue
            path = Path(source.path)
            if not path.is_file():
                continue
            knowledge = _read_knowledge(path)
            key = _topic_key(knowledge.topic)
            if key in known_topics:
                continue
            loaded.append(_LoadedKnowledge(knowledge, path))
            known_topics.add(key)
        return loaded

    @staticmethod
    def _matching_knowledge(
        topic: str,
        retrieval: RetrievalResult,
        records: Sequence[_LoadedKnowledge],
    ) -> list[_LoadedKnowledge]:
        query_terms = parse_query(topic).terms
        candidate_ids = {candidate.document_id for candidate in retrieval.candidates}
        matches: list[tuple[float, _LoadedKnowledge]] = []
        for record in records:
            topic_terms = set(parse_query(record.knowledge.topic).terms)
            topic_matches = set(query_terms) & topic_terms
            linked_ids = {
                source.note_id
                for source in record.knowledge.sources
                if source.note_id in candidate_ids
            }
            if not topic_matches and not linked_ids:
                continue
            topic_score = len(topic_matches) / len(query_terms) if query_terms else 0.0
            link_score = len(linked_ids) / len(candidate_ids) if candidate_ids else 0.0
            score = min(1.0, (0.75 * topic_score) + (0.25 * link_score))
            matches.append((score, record))
        matches.sort(
            key=lambda item: (
                -item[0],
                item[1].knowledge.topic.casefold(),
                item[1].path.as_posix(),
            )
        )
        return [record for _, record in matches]

    def _resolve_note(
        self,
        candidate: RetrievalCandidate,
        index: IndexFile,
        loaded_notes: dict[str, NoteRecord],
        raw_id_by_note: dict[str, str],
    ) -> _ResolvedNote:
        record = loaded_notes.get(candidate.document_id)
        if record is None:
            path = _candidate_path(
                candidate,
                index,
                index_path=self.index_path,
                notes_dir=self.notes_dir,
            )
            record = _read_candidate_note(path, candidate.document_id)
        else:
            path = record.path

        raw_id = raw_id_by_note.get(candidate.document_id, candidate.raw_document_id)
        if record is not None:
            note = record.note
            raw_id = raw_id_by_note.get(
                candidate.document_id,
                _raw_id_from_reference(note.source_reference, raw_id),
            )
            return _ResolvedNote(
                document_id=candidate.document_id,
                raw_document_id=raw_id,
                note=note,
                path=path,
                title=note.title,
                reference=_clean(note.source_reference) or f"raw:{raw_id}",
            )

        fallback = path
        try:
            stored = NoteStorage(self.notes_dir).read_if_exists(candidate.document_id)
        except (OSError, NoteFormatError, NoteStorageError, ValueError) as exc:
            raise ScriptStorageError(
                f"Could not read Note {candidate.document_id!r}: {self.notes_dir}"
            ) from exc
        if stored is not None:
            note = stored.note
            raw_id = raw_id_by_note.get(
                candidate.document_id,
                _raw_id_from_reference(note.source_reference, raw_id),
            )
            return _ResolvedNote(
                document_id=candidate.document_id,
                raw_document_id=raw_id,
                note=note,
                path=stored.path,
                title=note.title,
                reference=_clean(note.source_reference) or f"raw:{raw_id}",
            )

        return _ResolvedNote(
            document_id=candidate.document_id,
            raw_document_id=raw_id,
            note=None,
            path=fallback,
            title=candidate.title,
            reference=f"raw:{raw_id}",
        )

    def _load_raw(self, resolved: _ResolvedNote) -> _RawMaterial | None:
        document_id = resolved.raw_document_id
        try:
            if not self.raw_storage.has_document(document_id):
                return None
            document = self.raw_storage.load_document(document_id)
            paths = self.raw_storage.paths_for(document_id)
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError, ValueError, RawStorageError) as exc:
            raise ScriptStorageError(f"Invalid Raw record: {document_id}") from exc
        if not document.content.strip():
            return None
        return _RawMaterial(
            document_id=document_id,
            title=resolved.title,
            content=document.content,
            original_path=paths.original_file,
            extracted_path=paths.extracted_text_file,
        )

    @staticmethod
    def _knowledge_source(record: _LoadedKnowledge) -> ScriptSource:
        topic = record.knowledge.topic
        return ScriptSource(
            kind="knowledge",
            source_id=f"knowledge:{topic}",
            title=topic,
            path=str(record.path),
            reference=str(record.path),
            role="compiled topic synthesis",
        )

    @staticmethod
    def _note_source(resolved: _ResolvedNote) -> ScriptSource:
        return ScriptSource(
            kind="note",
            source_id=resolved.document_id,
            title=resolved.title,
            path=str(resolved.path),
            reference=resolved.reference,
            role="retrieved Note evidence",
            available=resolved.note is not None,
        )

    @staticmethod
    def _raw_source(material: _RawMaterial) -> ScriptSource:
        return ScriptSource(
            kind="raw",
            source_id=material.document_id,
            title=material.title,
            path=str(material.original_path),
            reference=f"raw:{material.document_id}",
            role="raw text verification",
        )

    @staticmethod
    def _knowledge_evidence(
        record: _LoadedKnowledge,
        source: ScriptSource,
    ) -> ScriptEvidence:
        knowledge = record.knowledge
        return ScriptEvidence(
            source_id=source.source_id,
            source_kind="knowledge",
            explanation=(
                f"Topic Knowledge {knowledge.topic!r} supplied its persisted current synthesis."
            ),
            excerpt=knowledge.current_synthesis,
            path=source.path,
        )

    @staticmethod
    def _note_evidence(
        resolved: _ResolvedNote,
        source: ScriptSource,
    ) -> ScriptEvidence:
        assert resolved.note is not None
        note = resolved.note
        pieces = [note.summary, *note.key_points[:2]]
        if note.quotes:
            pieces.append(f"引用：{note.quotes[0]}")
        return ScriptEvidence(
            source_id=source.source_id,
            source_kind="note",
            explanation=f"Note {note.title!r} supplied its persisted summary and details.",
            excerpt=" ".join(pieces),
            path=source.path,
        )

    @staticmethod
    def _raw_evidence(
        material: _RawMaterial,
        source: ScriptSource,
    ) -> ScriptEvidence:
        return ScriptEvidence(
            source_id=source.source_id,
            source_kind="raw",
            explanation=(
                f"Raw document {material.document_id!r} was read locally for source-level verification."
            ),
            excerpt=material.content,
            path=source.path,
        )

    @staticmethod
    def _selection(
        value: SelectionInput | None,
        *,
        confirmed: bool | None,
    ) -> ScriptSelection:
        if value is None:
            return ScriptSelection(confirmed=False)
        if isinstance(value, ScriptSelection):
            selection = value.model_copy(deep=True)
            if confirmed is not None:
                selection.confirmed = confirmed
            return ScriptSelection.model_validate(selection)
        if isinstance(value, TopicCandidate):
            topic = value.title
            default_confirmed = True
            candidate = value
        elif isinstance(value, str):
            topic = _clean(value)
            if not topic:
                raise ScriptInputError("selected topic cannot be empty")
            default_confirmed = True
            candidate = None
        else:
            raise ScriptInputError(
                f"Unsupported selected topic input: {type(value).__name__}"
            )
        return ScriptSelection(
            confirmed=default_confirmed if confirmed is None else confirmed,
            topic=topic,
            identifier=topic,
            candidate=candidate,
        )

    @staticmethod
    def _raw_id_map(records: Sequence[_LoadedKnowledge]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for record in records:
            for source in record.knowledge.sources:
                mapping[source.note_id] = source.raw_document_id or source.note_id
        return mapping

def _sanitize_script_text(text: str) -> str:
    """Remove knowledge-base implementation labels from publishable copy."""

    cleaned = text
    for marker, replacement in _SCRIPT_MARKER_REPLACEMENTS.items():
        cleaned = cleaned.replace(marker, replacement)
    cleaned = re.sub(r"(?<!\w)#+\s*", "", cleaned)
    return re.sub(r"\b(?:raw|note|knowledge)\b", "材料", cleaned, flags=re.IGNORECASE)


def _make_script_title(topic: str) -> str:
    """Create a publishable, curiosity-driven title from the confirmed topic."""

    clean_topic = _sanitize_script_text(_excerpt(topic, limit=42)).strip("「」\"“”")
    return clean_topic


def _format_spoken_copy(text: str) -> str:
    """Keep Chinese/Latin boundaries readable without changing source names."""

    text = re.sub(r"([\u4e00-\u9fff])([A-Za-z0-9])", r"\1 \2", text)
    text = re.sub(r"([A-Za-z0-9])([\u4e00-\u9fff])", r"\1 \2", text)
    return text.replace("——", "--").replace("—", "--")


def _script_quality_issues(text: str, focus: str = "") -> list[str]:
    issues = []
    if not MIN_SCRIPT_CHARS <= len(text) <= MAX_SCRIPT_CHARS:
        issues.append(f"正文需为 {MIN_SCRIPT_CHARS}～{MAX_SCRIPT_CHARS} 字符，当前 {len(text)} 字符")
    if any(marker.casefold() in text.casefold() for marker in FORBIDDEN_SCRIPT_MARKERS) or re.search(
        r"本文|本篇|这篇文章|第[\d一二三四五六七八九十百]+篇|系列导航|来源\s*[\d一二三四五六七八九十]+|Title:|Summary:|Key points:", text,
    ):
        issues.append("正文混入文章介绍、系列编号或资料字段，需要改写成直接对观众说的话")
    if "…" in text or "..." in text:
        issues.append("不要用省略号截断材料或观点，句子必须完整")
    if focus and "".join(focus.casefold().split()) not in "".join(text.casefold().split()):
        issues.append(f"正文偏离已确认主线“{focus}”，请只围绕它展开")
    return issues


class ScriptWriter(_ScriptWriterCore):
    """Write scripts after a fresh local retrieval."""

    def _plan_visual_materials(self, topic: str, script: str) -> tuple[list[VisualMaterialSuggestion], str]:
        paragraphs = [part.strip() for part in script.split("\n\n") if part.strip()]
        for attempt in range(2):
            try:
                suggestions = self.provider.plan_visual_materials(topic, tuple(paragraphs))
                if not 3 <= len(suggestions) <= 5:
                    raise ValueError("material count must be 3–5")
                materials = [VisualMaterialSuggestion.model_validate(item) for item in suggestions]
                if any(item.paragraph > len(paragraphs) or any(not step.strip() for step in item.preparation) for item in materials):
                    raise ValueError("invalid paragraph or empty step")
                if len({item.visual.casefold() for item in materials}) != len(materials):
                    raise ValueError("duplicate shots")
                for item in materials:
                    item.visual = _format_spoken_copy(item.visual)
                    item.preparation = [_format_spoken_copy(step) for step in item.preparation]
                    item.tool = _format_spoken_copy(item.tool)
                    item.alternative = _format_spoken_copy(item.alternative)
                return materials, "以下是需补录或制作的拍摄建议，不是已生成的视频。已有资料仅可作为内容参考。"
            except Exception:
                if attempt:
                    return [], "素材清单两次请求或格式校验均未通过；合格口播稿已保留。请稍后重新生成。"
        return [], "素材清单未生成；合格口播稿已保留。"

    def _write_script_text(
        self,
        topic: str,
        context: Sequence[ProviderDocument],
        focus: str = "",
    ) -> str:
        issues = []
        for attempt in range(2):
            instruction = topic + (f"\n唯一口播主线：{focus}" if focus else "")
            if attempt:
                instruction += "\n编辑修订要求（不要写进口播）：" + "；".join(issues)
            try:
                generated = self.provider.write_script(instruction, tuple(context), target_seconds=TARGET_SECONDS)
            except Exception as exc:
                raise ScriptProviderError("Provider could not write a script from local evidence") from exc
            candidate = _format_spoken_copy(generated.strip()) if isinstance(generated, str) else ""
            issues = _script_quality_issues(candidate, focus)
            if not issues:
                return candidate
        raise ScriptQualityError("；".join(issues))

    def write(
        self,
        selected_topic: SelectionInput | None = None,
        *,
        topic: SelectionInput | None = None,
        selected: SelectionInput | None = None,
        topic_id: str | None = None,
        confirmed: bool | None = None,
        user_confirmed: bool | None = None,
        limit: int | None = DEFAULT_LIMIT,
    ) -> ScriptResult:
        """Write a script only after a topic selection has been confirmed."""

        values = [
            value
            for value in (selected_topic, topic, selected, topic_id)
            if value is not None
        ]
        if len(values) > 1:
            raise ScriptInputError(
                "provide only one of selected_topic, topic, selected, or topic_id"
            )
        if confirmed is not None and user_confirmed is not None:
            if confirmed != user_confirmed:
                raise ScriptInputError(
                    "confirmed and user_confirmed must agree when both are provided"
                )
        effective_confirmed = (
            user_confirmed if user_confirmed is not None else confirmed
        )
        value = values[0] if values else None
        selection = self._selection(value, confirmed=effective_confirmed)
        topic_text = selection.topic
        empty_retrieval = RetrievalResult(query=topic_text or "", status="no_hits", candidates=[])

        if not selection.confirmed or not topic_text:
            return ScriptResult(
                topic=topic_text,
                status="not_confirmed",
                selection_confirmed=False,
                selection=selection,
                message=(
                    "未检测到用户明确确认的选题；请先选择一个 TopicCandidate，"
                    "再以 confirmed=True 或 CLI --confirm 重新请求。"
                ),
                retrieval=empty_retrieval,
            )
        if limit is not None and limit <= 0:
            raise ScriptInputError("limit must be greater than zero")

        focus = selection.candidate.focus if selection.candidate is not None else ""
        assert self.retrieval_service is not None
        try:
            # This is intentionally called on every confirmed write.  No
            # candidate retrieval result is cached from TopicGenerator.
            retrieval = self.retrieval_service.search(focus or topic_text, limit=limit)
        except (FileNotFoundError, IndexStorageError) as exc:
            raise ScriptStorageError("Could not retrieve the local JSON Index") from exc

        if focus and selection.candidate is not None:
            allowed_ids = {source.source_id for source in selection.candidate.sources if source.kind == "note"}
            selected = [item for item in retrieval.candidates if item.document_id in allowed_ids]
            retrieval = retrieval.model_copy(update={
                "candidates": selected,
                "status": "ok" if selected else "no_hits",
            })

        if not retrieval.candidates:
            return ScriptResult(
                topic=topic_text,
                status="no_hits",
                selection_confirmed=True,
                selection=selection,
                message=(
                    f"已确认选题“{topic_text}”，但二次检索没有找到匹配的本地 Index 证据；"
                    "未生成口播，也未补写事实。"
                ),
                retrieval=retrieval,
            )

        index = self._load_index()
        loaded_notes = self._load_notes(selection)
        loaded_knowledge = self._load_knowledge(selection)
        matched_knowledge = self._matching_knowledge(
            topic_text,
            retrieval,
            loaded_knowledge,
        )
        if focus:
            # Broad compiled themes can contain unrelated Notes. For a precise
            # editorial candidate, keep the selected Notes and their Raw only.
            matched_knowledge = []
        raw_id_by_note = self._raw_id_map(matched_knowledge)
        resolved_notes = [
            self._resolve_note(candidate, index, loaded_notes, raw_id_by_note)
            for candidate in retrieval.candidates
        ]
        raw_materials = [
            material
            for resolved in resolved_notes
            if (material := self._load_raw(resolved)) is not None
        ]

        source_map: dict[tuple[str, str], ScriptSource] = {}
        evidence: list[ScriptEvidence] = []
        context: list[ProviderDocument] = []

        for record in matched_knowledge:
            source = self._knowledge_source(record)
            source_map[(source.kind, source.source_id)] = source
            evidence.append(self._knowledge_evidence(record, source))
            context.append(_provider_knowledge(record))

        for resolved in resolved_notes:
            source = self._note_source(resolved)
            source_map[(source.kind, source.source_id)] = source
            if resolved.note is not None:
                evidence.append(self._note_evidence(resolved, source))
                context.append(_provider_note(resolved.note))

        for material in raw_materials:
            source = self._raw_source(material)
            source_map[(source.kind, source.source_id)] = source
            evidence.append(self._raw_evidence(material, source))
            context.append(_provider_raw(material))

        if not context:
            return ScriptResult(
                topic=topic_text,
                status="insufficient_evidence",
                selection_confirmed=True,
                selection=selection,
                message=(
                    "已确认选题且二次检索命中 Index，但没有可读取的 Knowledge、Note 或 Raw 内容；"
                    "证据不足，未生成口播。"
                ),
                retrieval=retrieval,
                sources=list(source_map.values()),
                evidence=evidence,
            )

        try:
            script = self._write_script_text(
                topic_text, tuple(context), focus=focus,
            )
        except ScriptQualityError as exc:
            return ScriptResult(
                topic=topic_text, status="quality_failed", selection_confirmed=True,
                selection=selection,
                message=f"口播经一次针对性重写仍未通过质量检查：{exc}。请重新生成或换一个更具体的选题。",
                retrieval=retrieval, sources=list(source_map.values()), evidence=evidence,
            )
        visual_materials, visual_message = self._plan_visual_materials(topic_text, script)
        return ScriptResult(
            topic=topic_text,
            title=_make_script_title(topic_text),
            status="generated",
            selection_confirmed=True,
            selection=selection,
            script=script,
            visual_materials=visual_materials,
            visual_materials_message=visual_message,
            message=(
                f"已确认选题并完成二次本地检索；口播基于 {len(context)} 份可读取证据生成，"
                "通过已配置的 AI 服务生成，仅使用本次选中的本地材料。"
            ),
            retrieval=retrieval,
            sources=list(source_map.values()),
            evidence=evidence,
        )

    write_script = write
    generate = write
    generate_script = write


ScriptService = ScriptWriter
ScriptGenerationService = ScriptWriter


def write_script(
    selected_topic: SelectionInput | None = None,
    *,
    topic: SelectionInput | None = None,
    selected: SelectionInput | None = None,
    topic_id: str | None = None,
    confirmed: bool | None = None,
    user_confirmed: bool | None = None,
    provider: AIProvider | None = None,
    index: IndexInput | None = None,
    index_path: str | Path | None = None,
    knowledge: KnowledgeInput | Sequence[KnowledgeInput] | None = None,
    knowledge_dir: str | Path | None = None,
    notes: NoteInput | Sequence[NoteInput] | None = None,
    notes_dir: str | Path | None = None,
    raw_dir: str | Path | None = None,
    raw_storage: RawStorage | None = None,
    retrieval: RetrievalService | None = None,
    retrieval_service: RetrievalService | None = None,
    limit: int | None = DEFAULT_LIMIT,
) -> ScriptResult:
    """Write one script through the configured local stores."""

    return ScriptWriter(
        index=index,
        index_path=index_path,
        knowledge=knowledge,
        knowledge_dir=knowledge_dir,
        notes=notes,
        notes_dir=notes_dir,
        raw_dir=raw_dir,
        raw_storage=raw_storage,
        retrieval=retrieval,
        retrieval_service=retrieval_service,
        provider=provider,
    ).write(
        selected_topic,
        topic=topic,
        selected=selected,
        topic_id=topic_id,
        confirmed=confirmed,
        user_confirmed=user_confirmed,
        limit=limit,
    )


generate_script = write_script
create_script = write_script


__all__ = [
    "DEFAULT_LIMIT",
    "IndexInput",
    "KnowledgeInput",
    "MAX_SCRIPT_CHARS",
    "MIN_SCRIPT_CHARS",
    "NoteInput",
    "ScriptGenerationError",
    "ScriptGenerationService",
    "ScriptInputError",
    "ScriptProviderError",
    "ScriptService",
    "ScriptStorageError",
    "ScriptWriter",
    "SelectionInput",
    "TARGET_SECONDS",
    "create_script",
    "generate_script",
    "write_script",
]
