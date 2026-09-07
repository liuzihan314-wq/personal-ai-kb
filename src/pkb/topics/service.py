"""Generate deterministic, traceable content topics from the local KB.

The service reads the existing Index, Notes, and Topic Knowledge files.  It
does not write any of them, call a Provider, use a network, or require a
vector store.  Topic titles are deliberately assembled from visible local
signals and fixed editorial angle templates rather than invented by a model.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Literal, TypeAlias

from pkb.config import get_settings
from pkb.index.keywords import clean_values, extract_keywords, normalize_term, tokenize_text
from pkb.index.model import IndexEntry, IndexFile
from pkb.index.storage import IndexStorageError, read_index
from pkb.knowledge.markdown import KnowledgeFormatError, parse_knowledge
from pkb.knowledge.model import TopicKnowledge
from pkb.knowledge.storage import KnowledgeRecord
from pkb.notes.markdown import NoteFormatError, parse_note
from pkb.notes.model import Note
from pkb.notes.storage import NoteRecord
from pkb.topics.model import (
    TopicCandidate,
    TopicEvidence,
    TopicGenerationResult,
    TopicReason,
    TopicSource,
)


class TopicGenerationError(ValueError):
    """Raised when local topic-generation inputs are not trustworthy."""


IndexInput: TypeAlias = IndexFile | str | Path
NoteInput: TypeAlias = Note | NoteRecord | str | Path
KnowledgeInput: TypeAlias = TopicKnowledge | KnowledgeRecord | str | Path


RECENT_DAYS = 30
DEFAULT_LIMIT = 5
MAX_LIMIT = 5
_SIGNAL_PRIORITY = {
    "knowledge": 0,
    "topic": 1,
    "tag": 2,
    "keyword": 3,
    "title": 4,
}
_EVIDENCE_ORDER = (
    "knowledge",
    "topic",
    "tag",
    "keyword",
    "title",
    "idea_card",
    "quote",
    "recent_material",
)
_IDEA_TYPES = frozenset({"idea", "quote", "inspiration", "judgment"})


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _canonical(value: str) -> str:
    tokens = tokenize_text(value)
    if tokens:
        return " ".join(sorted(set(tokens)))
    return normalize_term(value)


def _clean_label(value: str) -> str:
    return " ".join(value.split()).strip()


def _source_key(kind: Literal["knowledge", "note"], source_id: str) -> str:
    return f"{kind}:{source_id}"


@dataclass(frozen=True)
class _Signal:
    key: str
    kind: str
    label: str


@dataclass
class _SourceData:
    key: str
    kind: Literal["knowledge", "note"]
    source_id: str
    title: str
    path: str
    reference: str
    content_type: str
    created_at: datetime | None
    note_ids: set[str] = field(default_factory=set)
    signals: list[_Signal] = field(default_factory=list)
    quotes: list[str] = field(default_factory=list)
    is_idea: bool = False


@dataclass
class _SeedGroup:
    key: str
    signals: list[tuple[str, str, str]] = field(default_factory=list)
    source_keys: set[str] = field(default_factory=set)

    def add(self, signal: _Signal, source_key: str) -> None:
        item = (signal.kind, signal.label, source_key)
        if item not in self.signals:
            self.signals.append(item)
        self.source_keys.add(source_key)


@dataclass(frozen=True)
class _LoadedNote:
    note: Note
    path: str


@dataclass(frozen=True)
class _LoadedKnowledge:
    knowledge: TopicKnowledge
    path: str


def _primary_signal(group: _SeedGroup) -> tuple[str, str, str]:
    """Select a human-readable label without depending on input order."""

    return min(
        group.signals,
        key=lambda item: (
            _SIGNAL_PRIORITY.get(item[0], 99),
            -len(tokenize_text(item[1])),
            normalize_term(item[1]),
            item[2],
        ),
    )


def _read_note(path: Path) -> Note:
    try:
        return parse_note(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, NoteFormatError) as exc:
        raise TopicGenerationError(f"Invalid Note file: {path}") from exc


def _read_knowledge(path: Path) -> TopicKnowledge:
    try:
        return parse_knowledge(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, KnowledgeFormatError) as exc:
        raise TopicGenerationError(f"Invalid Knowledge file: {path}") from exc


def _as_sequence(value: object) -> list[object]:
    if isinstance(value, (str, Path)):
        return [value]
    if isinstance(value, Sequence):
        return list(value)
    try:
        return list(iter(value))  # type: ignore[arg-type]
    except TypeError as exc:
        raise TopicGenerationError("Input must be a model, path, or sequence") from exc


def _note_files(path: Path) -> list[Path]:
    if not path.exists():
        raise TopicGenerationError(f"Notes path does not exist: {path}")
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise TopicGenerationError(f"Notes path is not a directory: {path}")
    return sorted(
        (item for item in path.rglob("*.md") if item.is_file()),
        key=lambda item: item.as_posix(),
    )


def _knowledge_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise TopicGenerationError(f"Knowledge path is not a directory: {path}")
    return sorted(
        (item for item in path.rglob("*.md") if item.is_file()),
        key=lambda item: item.as_posix(),
    )


def _note_index_entry(loaded: _LoadedNote, notes_dir: str) -> IndexEntry:
    note = loaded.note
    return IndexEntry(
        document_id=note.document_id,
        title=note.title,
        created_at=note.created_at,
        content_type=note.content_type,
        tags=clean_values(note.tags),
        keywords=extract_keywords(note),
        source_type=note.source_type,
        note_path=loaded.path or f"note:{note.document_id}",
        topic=None,
    )


def _load_notes(value: object | None) -> dict[str, _LoadedNote]:
    if value is None:
        return {}

    loaded: dict[str, _LoadedNote] = {}
    items = _as_sequence(value)
    for item in items:
        if isinstance(item, NoteRecord):
            parsed = _LoadedNote(item.note, str(item.path))
            candidates = [parsed]
        elif isinstance(item, Note):
            candidates = [_LoadedNote(item, f"note:{item.document_id}")]
        elif isinstance(item, (str, Path)):
            path = Path(item)
            candidates = [
                _LoadedNote(_read_note(file_path), str(file_path))
                for file_path in _note_files(path)
            ]
        else:
            raise TopicGenerationError(
                f"Unsupported Notes input: {type(item).__name__}"
            )

        for parsed in candidates:
            document_id = parsed.note.document_id
            if document_id in loaded and loaded[document_id].path != parsed.path:
                raise TopicGenerationError(f"Duplicate source Note ID: {document_id}")
            loaded[document_id] = parsed
    return loaded


def _load_knowledge(value: object | None) -> list[_LoadedKnowledge]:
    if value is None:
        return []

    loaded: list[_LoadedKnowledge] = []
    seen_topics: set[str] = set()
    for item in _as_sequence(value):
        if isinstance(item, KnowledgeRecord):
            candidates = [_LoadedKnowledge(item.knowledge, str(item.path))]
        elif isinstance(item, TopicKnowledge):
            candidates = [_LoadedKnowledge(item, f"knowledge:{_canonical(item.topic)}")]
        elif isinstance(item, (str, Path)):
            path = Path(item)
            candidates = [
                _LoadedKnowledge(_read_knowledge(file_path), str(file_path))
                for file_path in _knowledge_files(path)
            ]
        else:
            raise TopicGenerationError(
                f"Unsupported Knowledge input: {type(item).__name__}"
            )

        for parsed in candidates:
            topic_key = _canonical(parsed.knowledge.topic)
            if topic_key in seen_topics:
                raise TopicGenerationError(
                    f"Duplicate Topic Knowledge topic: {parsed.knowledge.topic}"
                )
            seen_topics.add(topic_key)
            loaded.append(parsed)
    return loaded


def _index_from_notes(notes: Iterable[_LoadedNote], notes_dir: str) -> IndexFile:
    entries = [
        _note_index_entry(note, notes_dir)
        for note in sorted(notes, key=lambda item: item.note.document_id)
    ]
    return IndexFile(notes_dir=notes_dir or "notes", entries=entries)


def _find_note_path(
    entry: IndexEntry,
    *,
    index: IndexFile,
    index_path: Path | None,
    notes_dir: Path | None,
) -> Path | None:
    raw_path = Path(entry.note_path)
    candidates: list[Path] = [raw_path]
    if raw_path.is_absolute():
        candidates = [raw_path]
    else:
        if notes_dir is not None:
            candidates.extend((notes_dir / raw_path, notes_dir / raw_path.name))
        index_notes_dir = Path(index.notes_dir)
        candidates.extend((index_notes_dir / raw_path, index_notes_dir / raw_path.name))
        if index_path is not None:
            candidates.extend(
                (index_path.parent / raw_path, index_path.parent / raw_path.name)
            )
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            return candidate
    return None


def _signal(kind: str, value: str) -> _Signal | None:
    label = _clean_label(value)
    key = _canonical(label)
    if not label or not key:
        return None
    return _Signal(key=key, kind=kind, label=label)


def _signals_for_entry(entry: IndexEntry, note: Note | None) -> list[_Signal]:
    signals: list[_Signal] = []
    values: list[tuple[str, str]] = []
    if entry.topic:
        values.append(("topic", entry.topic))
    values.extend(("tag", value) for value in entry.tags)
    values.extend(("keyword", value) for value in entry.keywords)
    if note is not None:
        values.extend(("tag", value) for value in note.tags)
        values.extend(("keyword", value) for value in extract_keywords(note, limit=8))
    values.extend(("title", token) for token in tokenize_text(entry.title))

    seen: set[tuple[str, str]] = set()
    for kind, value in values:
        current = _signal(kind, value)
        if current is None or (current.kind, current.key) in seen:
            continue
        signals.append(current)
        seen.add((current.kind, current.key))
    return signals


def _note_source(entry: IndexEntry, loaded: _LoadedNote | None) -> _SourceData:
    note = loaded.note if loaded is not None else None
    title = entry.title or (note.title if note is not None else entry.document_id)
    content_type = entry.content_type or (note.content_type if note is not None else "")
    created_at = entry.created_at or (note.created_at if note is not None else None)
    path = entry.note_path or (loaded.path if loaded is not None else "")
    path = path or f"note:{entry.document_id}"
    reference = note.source_reference.strip() if note is not None else ""
    reference = reference or f"raw:{entry.document_id}"
    quotes = list(note.quotes) if note is not None else []
    normalized_content_type = content_type.casefold().strip()
    is_idea = normalized_content_type in _IDEA_TYPES or (
        note is not None
        and (note.original_content is not None or note.content_type.casefold() in _IDEA_TYPES)
    )
    return _SourceData(
        key=_source_key("note", entry.document_id),
        kind="note",
        source_id=entry.document_id,
        title=title,
        path=path,
        reference=reference,
        content_type=content_type,
        created_at=created_at,
        note_ids={entry.document_id},
        signals=_signals_for_entry(entry, note),
        quotes=quotes,
        is_idea=is_idea,
    )


def _knowledge_source(loaded: _LoadedKnowledge) -> _SourceData:
    knowledge = loaded.knowledge
    source_id = f"knowledge:{_canonical(knowledge.topic)}"
    path = loaded.path or source_id
    return _SourceData(
        key=_source_key("knowledge", source_id),
        kind="knowledge",
        source_id=source_id,
        title=knowledge.topic,
        path=path,
        reference=path,
        content_type="knowledge",
        created_at=knowledge.updated_at,
        note_ids=set(knowledge.source_note_ids),
        signals=[_signal("knowledge", knowledge.topic)],
    )


def _display_source(source: _SourceData) -> TopicSource:
    return TopicSource(
        kind=source.kind,
        source_id=source.source_id,
        title=source.title,
        path=source.path,
        reference=source.reference,
        content_type=source.content_type,
    )


class TopicGenerator:
    """Generate ranked topic candidates from local, traceable signals."""

    def __init__(
        self,
        index: IndexInput | None = None,
        knowledge: KnowledgeInput | Sequence[KnowledgeInput] | None = None,
        notes: NoteInput | Sequence[NoteInput] | None = None,
        *,
        index_path: str | Path | None = None,
        knowledge_dir: str | Path | None = None,
        notes_dir: str | Path | None = None,
        clock: Callable[[], datetime] | None = None,
        recent_days: int = RECENT_DAYS,
    ) -> None:
        if index is not None and index_path is not None:
            raise ValueError("Pass index or index_path, not both")
        if knowledge is not None and knowledge_dir is not None:
            raise ValueError("Pass knowledge or knowledge_dir, not both")
        if notes is not None and notes_dir is not None:
            raise ValueError("Pass notes or notes_dir, not both")
        if recent_days <= 0:
            raise ValueError("recent_days must be greater than zero")

        self.index_input = index
        self.index_path = Path(index_path) if index_path is not None else None
        self.knowledge_input = knowledge
        self.knowledge_dir = Path(knowledge_dir) if knowledge_dir is not None else None
        self.notes_input = notes
        self.notes_dir = Path(notes_dir) if notes_dir is not None else None
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.recent_days = recent_days

    def _load_index(self) -> IndexFile | None:
        if self.index_input is not None:
            if isinstance(self.index_input, IndexFile):
                return self.index_input
            index_path = Path(self.index_input)
            try:
                return read_index(index_path)
            except FileNotFoundError as exc:
                raise TopicGenerationError(f"JSON Index does not exist: {index_path}") from exc
            except IndexStorageError as exc:
                raise TopicGenerationError(f"Invalid JSON Index: {index_path}") from exc
        if self.index_path is None:
            return None
        try:
            return read_index(self.index_path)
        except FileNotFoundError as exc:
            raise TopicGenerationError(f"JSON Index does not exist: {self.index_path}") from exc
        except IndexStorageError as exc:
            raise TopicGenerationError(f"Invalid JSON Index: {self.index_path}") from exc

    def _load_all(self) -> tuple[IndexFile, dict[str, _LoadedNote], list[_LoadedKnowledge]]:
        notes = _load_notes(self.notes_input)
        if self.notes_input is None and self.notes_dir is not None and self.notes_dir.exists():
            notes = _load_notes(self.notes_dir)

        index = self._load_index()
        if index is None:
            index = _index_from_notes(notes.values(), str(self.notes_dir or "notes"))
        else:
            # Index fields remain authoritative.  Notes only enrich signals such
            # as quotes, original idea text, and the exact source reference.
            for entry in index.entries:
                if entry.document_id not in notes:
                    note_path = _find_note_path(
                        entry,
                        index=index,
                        index_path=self.index_path,
                        notes_dir=self.notes_dir,
                    )
                    if note_path is not None:
                        parsed = _read_note(note_path)
                        if parsed.document_id != entry.document_id:
                            raise TopicGenerationError(
                                f"Index Note ID does not match its file: {note_path}"
                            )
                        notes[entry.document_id] = _LoadedNote(parsed, str(note_path))

            # Notes supplied separately are formal inputs too; include an entry
            # for one that is not yet present in the Index without persisting it.
            extra_entries = [
                _note_index_entry(loaded, str(self.notes_dir or index.notes_dir))
                for document_id, loaded in notes.items()
                if document_id not in {entry.document_id for entry in index.entries}
            ]
            if extra_entries:
                index = index.model_copy(update={"entries": [*index.entries, *extra_entries]})

        knowledge_value: object | None = self.knowledge_input
        if knowledge_value is None and self.knowledge_dir is not None:
            knowledge_value = self.knowledge_dir
        knowledge = _load_knowledge(knowledge_value)
        return index, notes, knowledge

    @staticmethod
    def _expand_group_sources(
        source_keys: set[str],
        sources: dict[str, _SourceData],
        notes_by_id: dict[str, _SourceData],
    ) -> set[str]:
        expanded = set(source_keys)
        for source_key in tuple(source_keys):
            source = sources[source_key]
            for note_id in source.note_ids:
                note_source = notes_by_id.get(note_id)
                if note_source is not None:
                    expanded.add(note_source.key)
        return expanded

    @staticmethod
    def _group_sources(
        group: _SeedGroup,
        sources: dict[str, _SourceData],
        notes_by_id: dict[str, _SourceData],
    ) -> set[str]:
        return TopicGenerator._expand_group_sources(group.source_keys, sources, notes_by_id)

    @staticmethod
    def _source_note_ids(
        source_keys: Iterable[str],
        sources: dict[str, _SourceData],
    ) -> set[str]:
        note_ids: set[str] = set()
        for source_key in source_keys:
            source = sources[source_key]
            if source.kind == "note":
                note_ids.update(source.note_ids)
            else:
                note_ids.update(source.note_ids)
        return note_ids

    def _secondary_group(
        self,
        primary: _SeedGroup,
        groups: dict[str, _SeedGroup],
        group_sources: dict[str, set[str]],
        sources: dict[str, _SourceData],
    ) -> _SeedGroup | None:
        options: list[tuple[tuple[object, ...], _SeedGroup]] = []
        primary_sources = group_sources[primary.key]
        primary_note_ids = self._source_note_ids(primary_sources, sources)
        for key, group in groups.items():
            if key == primary.key:
                continue
            overlap = primary_sources & group_sources[key]
            overlap_notes = primary_note_ids & self._source_note_ids(group_sources[key], sources)
            if not overlap_notes:
                continue
            selected = _primary_signal(group)
            options.append(
                (
                    (
                        -len(overlap_notes),
                        _SIGNAL_PRIORITY.get(selected[0], 99),
                        -len(tokenize_text(selected[1])),
                        normalize_term(selected[1]),
                        key,
                    ),
                    group,
                )
            )
        if not options:
            return None
        return min(options, key=lambda item: item[0])[1]

    @staticmethod
    def _evidence(
        signal: str,
        values: Iterable[str],
        source_ids: Iterable[str],
        explanation: str,
    ) -> TopicEvidence | None:
        cleaned_values = sorted({value for value in values if value})
        cleaned_source_ids = sorted({value for value in source_ids if value})
        if not cleaned_values or not cleaned_source_ids:
            return None
        return TopicEvidence(
            signal=signal,
            values=cleaned_values,
            source_ids=cleaned_source_ids,
            explanation=explanation,
        )

    def _build_candidate(
        self,
        primary: _SeedGroup,
        secondary: _SeedGroup | None,
        *,
        group_sources: dict[str, set[str]],
        sources: dict[str, _SourceData],
    ) -> TopicCandidate | None:
        primary_signal = _primary_signal(primary)
        secondary_signal = _primary_signal(secondary) if secondary is not None else None
        source_keys = set(group_sources[primary.key])
        if secondary is not None:
            # A secondary signal must co-occur with the primary one; do not
            # pull unrelated records merely because the secondary label is
            # broad (for example, a generic ``AI`` keyword).
            source_keys.update(group_sources[secondary.key] & source_keys)
        source_keys = {
            key for key in source_keys if key in sources
        }
        note_ids = self._source_note_ids(source_keys, sources)
        if len(note_ids) < 2:
            return None

        note_sources = [
            source
            for source in sources.values()
            if source.key in source_keys and source.kind == "note"
        ]
        knowledge_sources = [
            source
            for source in sources.values()
            if source.key in source_keys and source.kind == "knowledge"
        ]
        idea_sources = [source for source in note_sources if source.is_idea]
        recent_cutoff = _utc(self.clock()) - timedelta(days=self.recent_days)
        recent_sources = [
            source
            for source in note_sources
            if source.created_at is not None and _utc(source.created_at) >= recent_cutoff
        ]

        base_signals: dict[str, tuple[set[str], set[str]]] = defaultdict(
            lambda: (set(), set())
        )

        def add_signal(signal: str, value: str, source_id: str) -> None:
            values, ids = base_signals[signal]
            values.add(value)
            ids.add(source_id)

        for group in (primary, secondary):
            if group is None:
                continue
            for kind, label, source_key in group.signals:
                if source_key not in source_keys:
                    continue
                add_signal(kind, label, sources[source_key].source_id)

        if knowledge_sources:
            for source in knowledge_sources:
                add_signal("knowledge", source.title, source.source_id)
        for source in idea_sources:
            add_signal("idea_card", source.title, source.source_id)
        quote_sources = [source for source in note_sources if source.quotes]
        for source in quote_sources:
            for quote in source.quotes[:2]:
                add_signal("quote", quote, source.source_id)
        for source in recent_sources:
            date = _utc(source.created_at).date().isoformat() if source.created_at else "unknown"
            add_signal("recent_material", f"{source.title} ({date})", source.source_id)

        # The candidate must combine at least two actual local signal types;
        # a lone title token is never enough to create a topic.
        base_signal_names = {
            signal
            for signal in base_signals
            if signal not in {"recent_material", "idea_card", "quote", "knowledge"}
        }
        visible_signal_names = set(base_signal_names)
        visible_signal_names.update(
            signal
            for signal in ("knowledge" if knowledge_sources else "", "idea_card" if idea_sources else "")
            if signal
        )
        if len(visible_signal_names) < 2:
            return None

        primary_label = primary_signal[1]
        secondary_label = secondary_signal[1] if secondary_signal is not None else ""
        if secondary_label and _canonical(primary_label) != _canonical(secondary_label):
            topic_stem = f"{primary_label} × {secondary_label}"
        else:
            topic_stem = primary_label

        if idea_sources:
            angle = "把个人判断落到可执行流程"
        elif knowledge_sources:
            angle = "从多篇资料到可执行方法"
        elif len({source.content_type for source in note_sources if source.content_type}) > 1:
            angle = "不同路径如何取舍"
        else:
            angle = "从方法到实际应用"
        title = f"{topic_stem}：{angle}"

        supporting_titles = sorted({source.title for source in note_sources if source.title})
        title_preview = "、".join(supporting_titles[:3])
        source_preview = ", ".join(sorted(note_ids))
        clauses = [
            f"{len(note_ids)} 个本地来源共同覆盖“{primary_label}”",
        ]
        if secondary_label and _canonical(primary_label) != _canonical(secondary_label):
            clauses.append(f"并同时出现“{secondary_label}”信号")
        if knowledge_sources:
            clauses.append(
                f"已有 Topic Knowledge「{knowledge_sources[0].title}」把这些 Notes 组织成主题"
            )
        if idea_sources:
            clauses.append(
                f"包含观点卡片「{idea_sources[0].title}」，能加入个人判断而非只复述资料"
            )
        if recent_sources:
            clauses.append(
                f"其中 {len(recent_sources)} 个来源在最近 {self.recent_days} 天新增"
            )
        why = "；".join(clauses) + f"。支持来源：{source_preview}。"
        if title_preview:
            why += f"可从「{title_preview}」进一步组织内容。"

        reasons: list[TopicReason] = []
        support_weight = round(0.25 * min(1.0, len(note_ids) / 3), 4)
        reasons.append(
            TopicReason(
                rule="multi_source_support",
                matches=sorted(note_ids),
                weight=support_weight,
                explanation=f"candidate is supported by {len(note_ids)} distinct local Notes",
            )
        )
        diversity_weight = round(0.20 * min(1.0, len(visible_signal_names) / 3), 4)
        reasons.append(
            TopicReason(
                rule="signal_diversity",
                matches=sorted(visible_signal_names),
                weight=diversity_weight,
                explanation=(
                    "candidate combines visible signals: "
                    + ", ".join(sorted(visible_signal_names))
                ),
            )
        )
        explicit_kind = primary_signal[0]
        explicit_weight = {
            "knowledge": 0.15,
            "topic": 0.15,
            "tag": 0.12,
            "keyword": 0.08,
            "title": 0.05,
        }.get(explicit_kind, 0.05)
        reasons.append(
            TopicReason(
                rule="explicit_local_label",
                matches=[primary_label],
                weight=explicit_weight,
                explanation=f"primary label comes from persisted {explicit_kind} metadata",
            )
        )
        if knowledge_sources:
            reasons.append(
                TopicReason(
                    rule="knowledge_support",
                    matches=[source.source_id for source in knowledge_sources],
                    weight=0.15,
                    explanation="an existing Topic Knowledge page supports and groups the source Notes",
                )
            )
        if idea_sources:
            reasons.append(
                TopicReason(
                    rule="idea_card_signal",
                    matches=[source.source_id for source in idea_sources],
                    weight=0.15,
                    explanation="a persisted idea/quote card contributes a personal viewpoint signal",
                )
            )
        if recent_sources:
            reasons.append(
                TopicReason(
                    rule="recent_material",
                    matches=[source.source_id for source in recent_sources],
                    weight=0.10,
                    explanation=(
                        f"source created within the recent {self.recent_days}-day window; "
                        "this is a moderate recency bonus"
                    ),
                )
            )

        score = round(min(1.0, sum(reason.weight for reason in reasons)), 4)
        evidence: list[TopicEvidence] = []
        for signal in _EVIDENCE_ORDER:
            values, ids = base_signals.get(signal, (set(), set()))
            item = self._evidence(
                signal,
                values,
                ids,
                f"{signal} observed in {', '.join(sorted(ids))}",
            )
            if item is not None:
                evidence.append(item)

        display_sources = sorted(
            (sources[key] for key in source_keys),
            key=lambda source: (0 if source.kind == "knowledge" else 1, source.source_id),
        )
        if not evidence or len(evidence) < 2:
            return None
        return TopicCandidate(
            title=title,
            why_worth_doing=why,
            score=score,
            sources=[_display_source(source) for source in display_sources],
            evidence=evidence,
            reasons=reasons,
        )

    def generate(self, *, limit: int = DEFAULT_LIMIT) -> TopicGenerationResult:
        """Return up to five stable, explainable candidates without writes."""

        if not 1 <= limit <= MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")

        index, loaded_notes, loaded_knowledge = self._load_all()
        source_map: dict[str, _SourceData] = {}
        notes_by_id: dict[str, _SourceData] = {}
        for entry in sorted(index.entries, key=lambda item: item.document_id):
            source = _note_source(entry, loaded_notes.get(entry.document_id))
            source_map[source.key] = source
            notes_by_id[entry.document_id] = source
        for loaded in loaded_knowledge:
            source = _knowledge_source(loaded)
            source_map[source.key] = source

        groups: dict[str, _SeedGroup] = {}
        for source in source_map.values():
            for signal in source.signals:
                group = groups.setdefault(signal.key, _SeedGroup(signal.key))
                group.add(signal, source.key)

        group_sources = {
            key: self._group_sources(group, source_map, notes_by_id)
            for key, group in groups.items()
        }
        candidates: list[TopicCandidate] = []
        for key in sorted(groups):
            group = groups[key]
            if len(self._source_note_ids(group_sources[key], source_map)) < 2:
                continue
            secondary = self._secondary_group(group, groups, group_sources, source_map)
            candidate = self._build_candidate(
                group,
                secondary,
                group_sources=group_sources,
                sources=source_map,
            )
            if candidate is not None:
                candidates.append(candidate)

        unique: dict[str, TopicCandidate] = {}
        for candidate in candidates:
            identity = normalize_term(candidate.title)
            previous = unique.get(identity)
            if previous is None or (
                candidate.score,
                candidate.title.casefold(),
            ) > (previous.score, previous.title.casefold()):
                unique[identity] = candidate
        ranked = sorted(
            unique.values(),
            key=lambda candidate: (-candidate.score, candidate.title.casefold()),
        )[:limit]
        if len(ranked) < 3:
            message = (
                f"本地资料目前只能形成 {len(ranked)} 个可解释候选，资料不足；"
                "未用虚构选题补齐到 3 个。"
            )
            status = "insufficient_data"
        else:
            message = f"已基于本地 Index、Notes 与 Topic Knowledge 生成 {len(ranked)} 个候选。"
            status = "ok"
        return TopicGenerationResult(status=status, candidates=ranked, message=message)

    generate_topics = generate
    build = generate
    rank = generate


def generate_topics(
    index: IndexInput | None = None,
    knowledge: KnowledgeInput | Sequence[KnowledgeInput] | None = None,
    notes: NoteInput | Sequence[NoteInput] | None = None,
    *,
    index_path: str | Path | None = None,
    knowledge_dir: str | Path | None = None,
    notes_dir: str | Path | None = None,
    limit: int = DEFAULT_LIMIT,
    clock: Callable[[], datetime] | None = None,
    recent_days: int = RECENT_DAYS,
) -> TopicGenerationResult:
    """Generate local topic candidates through the path/object facade."""

    settings = get_settings()
    if index is None and index_path is None and knowledge is None and notes is None:
        index_path = settings.index_dir / "index.json"
        knowledge_dir = settings.knowledge_dir
        notes_dir = settings.notes_dir
    return TopicGenerator(
        index=index,
        knowledge=knowledge,
        notes=notes,
        index_path=index_path,
        knowledge_dir=knowledge_dir,
        notes_dir=notes_dir,
        clock=clock,
        recent_days=recent_days,
    ).generate(limit=limit)


generate_topic_candidates = generate_topics
build_topics = generate_topics
TopicService = TopicGenerator
TopicGenerationResultType = TopicGenerationResult


__all__ = [
    "DEFAULT_LIMIT",
    "IndexInput",
    "KnowledgeInput",
    "MAX_LIMIT",
    "NoteInput",
    "RECENT_DAYS",
    "TopicGenerationError",
    "TopicGenerationResultType",
    "TopicGenerator",
    "TopicService",
    "build_topics",
    "generate_topic_candidates",
    "generate_topics",
]
