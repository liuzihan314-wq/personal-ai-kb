"""Local, explainable Q&A over persisted Knowledge, Notes, and Raw data."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pkb.config import get_settings
from pkb.index.keywords import normalize_term, tokenize_text
from pkb.index.model import IndexFile
from pkb.index.storage import IndexStorageError, read_index
from pkb.knowledge.markdown import KnowledgeFormatError
from pkb.knowledge.storage import KnowledgeRecord, KnowledgeStorage, KnowledgeStorageError
from pkb.notes.markdown import NoteFormatError, parse_note
from pkb.notes.model import Note
from pkb.notes.storage import NoteRecord, NoteStorage, NoteStorageError
from pkb.providers import (
    AIProvider,
    MockAIProvider,
    ProviderDocument,
    ProviderNotConfiguredError,
)
from pkb.retrieval.model import RetrievalCandidate, RetrievalResult
from pkb.retrieval.service import RetrievalService, parse_query
from pkb.storage import RawStorage, RawStorageError

from pkb.qa.model import (
    EvidenceLevel,
    QAEvidence,
    QAResult,
    QASource,
)


class QAError(ValueError):
    """Base error for invalid local Q&A inputs or persisted evidence."""


class QAInputError(QAError):
    """Raised when a question or service configuration is invalid."""


class QAStorageError(QAError):
    """Raised when local evidence cannot be read or validated safely."""


class QAProviderError(QAError):
    """Raised when the configured Provider cannot return an answer."""


@dataclass(frozen=True)
class _KnowledgeMatch:
    record: KnowledgeRecord
    topic_terms: tuple[str, ...]
    linked_note_ids: tuple[str, ...]
    score: float


@dataclass(frozen=True)
class _ResolvedNote:
    document_id: str
    raw_document_id: str
    note: Note | None
    path: Path | None
    title: str
    reference: str


@dataclass(frozen=True)
class _RawMaterial:
    document_id: str
    title: str
    content: str
    original_path: Path
    extracted_path: Path


def _knowledge_key(topic: str) -> str:
    """Return the retrieval identity for a Topic Knowledge page."""

    terms = tokenize_text(topic)
    return " ".join(sorted(set(terms))) if terms else normalize_term(topic)


def _excerpt(value: str, *, limit: int = 600) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _source_reference(note: Note | None, fallback: str) -> str:
    if note is not None and note.source_reference.strip():
        return note.source_reference.strip()
    return fallback or "raw:unknown"


def _note_provider_document(note: Note) -> ProviderDocument:
    """Build provider context from fields already persisted in a Note."""

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
        source=_source_reference(note, f"raw:{note.document_id}"),
    )


def _knowledge_provider_document(record: KnowledgeRecord) -> ProviderDocument:
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


class QAService:
    """Answer questions using only local, persisted evidence."""

    def __init__(
        self,
        index: IndexFile | str | Path | None = None,
        *,
        index_path: str | Path | None = None,
        knowledge_dir: str | Path | None = None,
        knowledge_storage: KnowledgeStorage | None = None,
        notes_dir: str | Path | None = None,
        note_storage: NoteStorage | None = None,
        raw_dir: str | Path | None = None,
        raw_storage: RawStorage | None = None,
        provider: AIProvider | None = None,
    ) -> None:
        settings = get_settings()
        if index is not None and index_path is not None:
            raise QAInputError("Pass index or index_path, not both")
        if knowledge_dir is not None and knowledge_storage is not None:
            raise QAInputError("Pass knowledge_dir or knowledge_storage, not both")
        if notes_dir is not None and note_storage is not None:
            raise QAInputError("Pass notes_dir or note_storage, not both")
        if raw_dir is not None and raw_storage is not None:
            raise QAInputError("Pass raw_dir or raw_storage, not both")

        if isinstance(index, IndexFile):
            self._index = index
            self.index_path: Path | None = None
        else:
            self._index = None
            self.index_path = Path(
                index if index is not None else index_path or settings.index_dir / "index.json"
            )

        self._notes_dir_explicit = notes_dir is not None or note_storage is not None
        self.notes_storage = note_storage or NoteStorage(
            notes_dir if notes_dir is not None else settings.notes_dir
        )
        self.knowledge_storage = knowledge_storage or KnowledgeStorage(
            knowledge_dir if knowledge_dir is not None else settings.knowledge_dir
        )
        self.raw_storage = raw_storage or RawStorage(
            raw_dir if raw_dir is not None else settings.raw_dir
        )
        self.provider = provider if provider is not None else MockAIProvider()

    def _load_index(self) -> IndexFile:
        if self._index is not None:
            return self._index
        assert self.index_path is not None
        try:
            return read_index(self.index_path)
        except FileNotFoundError:
            # Knowledge pages can answer a topic even when a rebuildable Index
            # has not been created yet.  Keep the absence visible in the
            # structured RetrievalResult instead of inventing candidates.
            return IndexFile(notes_dir=str(self.notes_storage.notes_dir))
        except IndexStorageError as exc:
            raise QAStorageError(str(exc)) from exc

    def _index_notes_dir(self, index: IndexFile) -> Path:
        if self._notes_dir_explicit:
            return self.notes_storage.notes_dir
        index_notes_dir = Path(index.notes_dir)
        if index_notes_dir.is_absolute():
            return index_notes_dir
        if self.index_path is not None:
            next_to_index = self.index_path.parent / index_notes_dir
            if next_to_index.exists():
                return next_to_index
        return index_notes_dir

    def _scan_knowledge(self) -> list[KnowledgeRecord]:
        directory = self.knowledge_storage.knowledge_dir
        if not directory.exists():
            return []
        if not directory.is_dir():
            raise QAStorageError(f"Knowledge path is not a directory: {directory}")

        try:
            paths = sorted(
                (path for path in directory.rglob("*.md") if path.is_file()),
                key=lambda path: path.as_posix(),
            )
        except OSError as exc:
            raise QAStorageError(f"Could not scan Knowledge directory: {directory}") from exc

        latest_by_topic: dict[str, KnowledgeRecord] = {}
        for path in paths:
            try:
                knowledge = self.knowledge_storage.read(path)
            except (FileNotFoundError, KnowledgeStorageError, KnowledgeFormatError) as exc:
                raise QAStorageError(f"Invalid Knowledge file: {path}") from exc
            record = KnowledgeRecord(knowledge=knowledge, path=path, created=False)
            key = _knowledge_key(knowledge.topic)
            existing = latest_by_topic.get(key)
            if existing is None or (
                record.knowledge.updated_at,
                record.knowledge.created_at,
                record.path.as_posix(),
            ) > (
                existing.knowledge.updated_at,
                existing.knowledge.created_at,
                existing.path.as_posix(),
            ):
                latest_by_topic[key] = record
        return [latest_by_topic[key] for key in sorted(latest_by_topic)]

    @staticmethod
    def _knowledge_matches(
        question: str,
        retrieval: RetrievalResult,
        records: list[KnowledgeRecord],
    ) -> list[_KnowledgeMatch]:
        query_terms = parse_query(question).terms
        candidate_ids = {candidate.document_id for candidate in retrieval.candidates}
        matches: list[_KnowledgeMatch] = []
        for record in records:
            topic_terms = set(tokenize_text(record.knowledge.topic))
            topic_matches = tuple(term for term in query_terms if term in topic_terms)
            source_ids = tuple(
                source.note_id
                for source in record.knowledge.sources
                if source.note_id in candidate_ids
            )
            if not topic_matches and not source_ids:
                continue
            topic_coverage = (
                len(set(topic_matches)) / len(query_terms) if query_terms else 0.0
            )
            source_coverage = (
                len(set(source_ids)) / len(candidate_ids) if candidate_ids else 0.0
            )
            score = min(1.0, (0.75 * topic_coverage) + (0.25 * source_coverage))
            matches.append(
                _KnowledgeMatch(
                    record=record,
                    topic_terms=topic_matches,
                    linked_note_ids=source_ids,
                    score=round(score, 4),
                )
            )
        matches.sort(
            key=lambda item: (
                -item.score,
                item.record.knowledge.topic.casefold(),
                item.record.path.as_posix(),
            )
        )
        return matches

    @staticmethod
    def _candidate_path(
        candidate: RetrievalCandidate,
        index: IndexFile,
        *,
        index_path: Path | None,
        notes_dir: Path,
    ) -> Path:
        path = Path(candidate.note_path)
        options: list[Path] = [path]
        if not path.is_absolute() and index_path is not None:
            options.append(index_path.parent / path)
        if not path.is_absolute():
            options.extend(
                [
                    notes_dir / path.name,
                    notes_dir / path,
                    Path(index.notes_dir) / path.name,
                    Path(index.notes_dir) / path,
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

    @staticmethod
    def _read_note_path(path: Path, document_id: str) -> NoteRecord | None:
        if not path.is_file():
            return None
        try:
            note = parse_note(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, NoteFormatError) as exc:
            raise QAStorageError(f"Invalid Note file: {path}") from exc
        if note.document_id != document_id:
            raise QAStorageError(f"Note ID does not match its path: {path}")
        return NoteRecord(note=note, path=path, created=False)

    def _resolve_note(
        self,
        document_id: str,
        *,
        candidate: RetrievalCandidate | None,
        raw_document_id: str | None = None,
        index: IndexFile,
    ) -> _ResolvedNote:
        resolved_raw_id = (
            raw_document_id
            or (candidate.raw_document_id if candidate is not None else None)
            or document_id
        )
        candidate_path = (
            self._candidate_path(
                candidate,
                index,
                index_path=self.index_path,
                notes_dir=self._index_notes_dir(index),
            )
            if candidate is not None
            else None
        )
        if candidate_path is not None:
            record = self._read_note_path(candidate_path, document_id)
            if record is not None:
                return _ResolvedNote(
                    document_id=document_id,
                    raw_document_id=resolved_raw_id,
                    note=record.note,
                    path=record.path,
                    title=record.note.title,
                    reference=_source_reference(record.note, f"raw:{document_id}"),
                )

        try:
            record = self.notes_storage.read_if_exists(document_id)
        except FileNotFoundError:
            record = None
        except NoteStorageError as exc:
            raise QAStorageError(
                f"Could not read Note {document_id!r}: {self.notes_storage.notes_dir}"
            ) from exc
        if record is not None:
            return _ResolvedNote(
                document_id=document_id,
                raw_document_id=resolved_raw_id,
                note=record.note,
                path=record.path,
                title=record.note.title,
                reference=_source_reference(record.note, f"raw:{document_id}"),
            )

        fallback_path = candidate_path or self.notes_storage.path_for(document_id)
        candidate_title = candidate.title if candidate is not None else document_id
        return _ResolvedNote(
            document_id=document_id,
            raw_document_id=resolved_raw_id,
            note=None,
            path=fallback_path,
            title=candidate_title,
            reference=f"raw:{document_id}",
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
            raise QAStorageError(f"Invalid Raw record: {document_id}") from exc
        if not document.content.strip():
            return None
        return _RawMaterial(
            document_id=document_id,
            title=resolved.note.title if resolved.note is not None else resolved.title,
            content=document.content,
            original_path=paths.original_file,
            extracted_path=paths.extracted_text_file,
        )

    @staticmethod
    def _note_source(resolved: _ResolvedNote, *, role: str) -> QASource:
        return QASource(
            kind="note",
            source_id=resolved.document_id,
            title=resolved.title,
            path=str(resolved.path) if resolved.path is not None else None,
            reference=resolved.reference,
            role=role,
            available=resolved.note is not None,
        )

    @staticmethod
    def _knowledge_source(record: KnowledgeRecord) -> QASource:
        topic = record.knowledge.topic
        return QASource(
            kind="knowledge",
            source_id=f"topic:{topic}",
            title=topic,
            path=str(record.path),
            reference=f"topic:{topic}",
            role="compiled topic synthesis",
        )

    @staticmethod
    def _raw_source(material: _RawMaterial) -> QASource:
        return QASource(
            kind="raw",
            source_id=material.document_id,
            title=material.title,
            path=str(material.original_path),
            reference=f"raw:{material.document_id}",
            role="raw text fallback and fact check",
        )

    @staticmethod
    def _knowledge_evidence(
        match: _KnowledgeMatch,
        source: QASource,
    ) -> QAEvidence:
        matched = ", ".join(match.topic_terms) or "linked Note IDs"
        return QAEvidence(
            source_id=source.source_id,
            source_kind="knowledge",
            explanation=(
                f"Topic Knowledge {match.record.knowledge.topic!r} supplied the current "
                f"synthesis; local matching evidence: {matched}."
            ),
            excerpt=_excerpt(match.record.knowledge.current_synthesis),
            path=source.path,
        )

    @staticmethod
    def _note_evidence(resolved: _ResolvedNote, source: QASource) -> QAEvidence:
        assert resolved.note is not None
        note = resolved.note
        detail = "summary"
        excerpt = note.summary
        if note.key_points:
            detail = "summary and key points"
            excerpt += " " + " ".join(note.key_points)
        return QAEvidence(
            source_id=source.source_id,
            source_kind="note",
            explanation=f"Note {note.title!r} contributed its persisted {detail}.",
            excerpt=_excerpt(excerpt),
            path=source.path,
        )

    @staticmethod
    def _raw_evidence(material: _RawMaterial, source: QASource) -> QAEvidence:
        return QAEvidence(
            source_id=source.source_id,
            source_kind="raw",
            explanation=(
                f"Raw document {material.document_id!r} was read locally as a fallback "
                "for source-level verification."
            ),
            excerpt=_excerpt(material.content),
            path=source.path,
        )

    @staticmethod
    def _evidence_level(
        knowledge: bool,
        notes: bool,
        raw: bool,
    ) -> EvidenceLevel:
        if knowledge and notes and raw:
            return "knowledge+notes+raw"
        if knowledge and notes:
            return "knowledge+notes"
        if knowledge and raw:
            return "knowledge+raw"
        if knowledge:
            return "knowledge"
        if notes and raw:
            return "notes+raw"
        if notes:
            return "notes"
        if raw:
            return "raw"
        return "none"

    @staticmethod
    def _merge_source(
        sources: dict[tuple[str, str], QASource],
        source: QASource,
    ) -> None:
        key = (source.kind, source.source_id)
        current = sources.get(key)
        if current is None:
            sources[key] = source
            return
        if not current.available and source.available:
            sources[key] = source
        elif not current.path and source.path:
            sources[key] = source

    def answer(self, question: str, *, limit: int | None = 10) -> QAResult:
        """Answer one question from local evidence without performing writes."""

        if not isinstance(question, str):
            raise QAInputError("question must be a string")
        if not question.strip():
            retrieval = RetrievalResult(query=question, status="no_hits", candidates=[])
            return QAResult(
                question=question,
                status="no_hits",
                reason="The question contains no searchable local terms.",
                retrieval=retrieval,
            )

        index = self._load_index()
        retrieval = RetrievalService(index).search(question, limit=limit)
        knowledge_matches = self._knowledge_matches(
            question,
            retrieval,
            self._scan_knowledge(),
        )

        candidate_by_id: Mapping[str, RetrievalCandidate] = {
            candidate.document_id: candidate for candidate in retrieval.candidates
        }
        note_ids: list[str] = []
        note_metadata: dict[str, tuple[str, str, str]] = {}
        for match in knowledge_matches:
            for source in match.record.knowledge.sources:
                if source.note_id not in note_metadata:
                    note_metadata[source.note_id] = (
                        source.title,
                        source.reference,
                        source.raw_document_id,
                    )
                if source.note_id not in note_ids:
                    note_ids.append(source.note_id)
        for candidate in retrieval.candidates:
            if candidate.document_id not in note_ids:
                note_ids.append(candidate.document_id)

        resolved_notes = [
            self._resolve_note(
                document_id,
                candidate=candidate_by_id.get(document_id),
                raw_document_id=note_metadata.get(document_id, ("", "", ""))[2] or None,
                index=index,
            )
            for document_id in note_ids
        ]
        resolved_notes = [
            _ResolvedNote(
                document_id=resolved.document_id,
                raw_document_id=resolved.raw_document_id,
                note=resolved.note,
                path=resolved.path,
                title=(resolved.note.title if resolved.note is not None else note_metadata.get(
                    resolved.document_id, (resolved.title, "", resolved.raw_document_id)
                )[0])
                or resolved.title,
                reference=(resolved.note.source_reference if resolved.note is not None else note_metadata.get(
                    resolved.document_id, ("", resolved.reference, resolved.raw_document_id)
                )[1])
                or resolved.reference,
            )
            for resolved in resolved_notes
        ]

        raw_materials: list[_RawMaterial] = []
        for resolved in resolved_notes:
            if resolved.note is not None:
                continue
            material = self._load_raw(resolved)
            if material is not None:
                raw_materials.append(material)

        source_map: dict[tuple[str, str], QASource] = {}
        evidence: list[QAEvidence] = []
        context: list[ProviderDocument] = []

        for match in knowledge_matches:
            source = self._knowledge_source(match.record)
            self._merge_source(source_map, source)
            evidence.append(self._knowledge_evidence(match, source))
            context.append(_knowledge_provider_document(match.record))

        for resolved in resolved_notes:
            role = (
                "Knowledge source Note"
                if any(
                    resolved.document_id in match.record.knowledge.source_note_ids
                    for match in knowledge_matches
                )
                else "retrieval candidate Note"
            )
            source = self._note_source(resolved, role=role)
            self._merge_source(source_map, source)
            if resolved.note is not None:
                evidence.append(self._note_evidence(resolved, source))
                context.append(_note_provider_document(resolved.note))

        for material in raw_materials:
            source = self._raw_source(material)
            self._merge_source(source_map, source)
            evidence.append(self._raw_evidence(material, source))
            context.append(
                ProviderDocument(
                    document_id=material.document_id,
                    title=material.title,
                    content=material.content,
                    source=str(material.extracted_path),
                )
            )

        sources = list(source_map.values())
        evidence_level = self._evidence_level(
            bool(knowledge_matches),
            any(resolved.note is not None for resolved in resolved_notes),
            bool(raw_materials),
        )
        if not context:
            if not retrieval.candidates and not knowledge_matches:
                return QAResult(
                    question=question,
                    status="no_hits",
                    reason="No matching Knowledge topic or Index candidate was found locally.",
                    retrieval=retrieval,
                    knowledge_topics=[match.record.knowledge.topic for match in knowledge_matches],
                    sources=sources,
                    evidence=evidence,
                )
            return QAResult(
                question=question,
                status="insufficient_evidence",
                reason=(
                    "Local retrieval found candidates, but no readable Knowledge, Note, "
                    "or Raw content was available as evidence."
                ),
                retrieval=retrieval,
                knowledge_topics=[match.record.knowledge.topic for match in knowledge_matches],
                sources=sources,
                evidence=evidence,
            )

        try:
            answer = self.provider.answer_question(question, tuple(context))
        except ProviderNotConfiguredError as exc:
            return QAResult(
                question=question,
                status="provider_not_configured",
                evidence_level=evidence_level,
                reason=str(exc),
                retrieval=retrieval,
                knowledge_topics=[match.record.knowledge.topic for match in knowledge_matches],
                sources=sources,
                evidence=evidence,
            )
        except Exception as exc:
            raise QAProviderError("Provider could not answer from local evidence") from exc
        if not isinstance(answer, str) or not answer.strip():
            raise QAProviderError("Provider returned an empty or invalid answer")

        return QAResult(
            question=question,
            status="answered",
            answer=answer.strip(),
            evidence_level=evidence_level,
            reason="Answer generated from the listed local evidence; no network retrieval was used.",
            retrieval=retrieval,
            knowledge_topics=[match.record.knowledge.topic for match in knowledge_matches],
            sources=sources,
            evidence=evidence,
        )

    ask = answer
    answer_question = answer
    synthesize = answer
    synthesize_topic = answer


QuestionAnswerService = QAService
TopicSynthesisService = QAService
QandAService = QAService


def answer_question(
    question: str,
    *,
    provider: AIProvider | None = None,
    index: IndexFile | str | Path | None = None,
    index_path: str | Path | None = None,
    knowledge_dir: str | Path | None = None,
    knowledge_storage: KnowledgeStorage | None = None,
    notes_dir: str | Path | None = None,
    note_storage: NoteStorage | None = None,
    raw_dir: str | Path | None = None,
    raw_storage: RawStorage | None = None,
    limit: int | None = 10,
) -> QAResult:
    """Answer one question using the configured local stores."""

    return QAService(
        index=index,
        index_path=index_path,
        knowledge_dir=knowledge_dir,
        knowledge_storage=knowledge_storage,
        notes_dir=notes_dir,
        note_storage=note_storage,
        raw_dir=raw_dir,
        raw_storage=raw_storage,
        provider=provider,
    ).answer(question, limit=limit)


ask_question = answer_question
qa = answer_question
synthesize_topic = answer_question


__all__ = [
    "QAError",
    "QAInputError",
    "QAProviderError",
    "QAService",
    "QAStorageError",
    "QandAService",
    "QuestionAnswerService",
    "TopicSynthesisService",
    "answer_question",
    "ask_question",
    "qa",
    "synthesize_topic",
]
