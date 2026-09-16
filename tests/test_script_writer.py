from datetime import datetime, timezone

from pkb.index import IndexEntry, IndexFile
from pkb.knowledge import KnowledgeSource, TopicKnowledge
from pkb.models import UnifiedDocument
from pkb.notes import Note, NoteStorage
from pkb.providers import MockAIProvider
from pkb.retrieval import RetrievalService
from pkb.scripts import (
    MAX_SCRIPT_CHARS,
    MIN_SCRIPT_CHARS,
    ScriptWriter,
)
from pkb.storage import RawStorage
from pkb.topics import TopicCandidate, TopicGenerator
from typer.testing import CliRunner

from pkb.cli.main import app


NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
runner = CliRunner()


def _note(document_id: str, title: str, summary: str, *, quote: str = "") -> Note:
    return Note(
        document_id=document_id,
        source_type="manual",
        title=title,
        created_at=NOW,
        content_type="idea",
        tags=["AI", "workflow"],
        summary=summary,
        key_points=[f"把“{title}”拆成一个可以验证的具体步骤。"],
        quotes=[quote] if quote else [],
        original_content=f"原始记录：{summary}",
        source_reference=f"raw:{document_id}",
    )


def _index(notes: list[Note]) -> IndexFile:
    return IndexFile(
        notes_dir="notes",
        entries=[
            IndexEntry(
                document_id=note.document_id,
                title=note.title,
                created_at=note.created_at,
                content_type=note.content_type,
                tags=note.tags,
                keywords=["AI", "workflow", "效率"],
                source_type=note.source_type,
                note_path=f"note:{note.document_id}",
                topic="AI 工作流",
            )
            for note in notes
        ],
    )


def _knowledge(notes: list[Note]) -> TopicKnowledge:
    return TopicKnowledge(
        topic="AI 工作流",
        created_at=notes[0].created_at,
        updated_at=NOW,
        source_note_ids=[note.document_id for note in notes],
        source_references=[note.source_reference for note in notes],
        synthesis="把 AI 工具放进可复用的工作流，并用结果验证取舍。",
        sources=[
            KnowledgeSource(
                note_id=note.document_id,
                title=note.title,
                raw_document_id=note.document_id,
                reference=note.source_reference,
            )
            for note in notes
        ],
    )


def _fixed_library(tmp_path):
    notes = [
        _note(
            "workflow-1",
            "AI 工作流：从工具到流程",
            "把 AI 工具组合成可复用的效率流程。",
            quote="先把任务拆成流程，再决定工具。",
        ),
        _note(
            "workflow-2",
            "自动化减少重复劳动",
            "自动化要嵌入工作流，先验证具体任务的收益。",
        ),
        _note(
            "workflow-3",
            "先改流程，再换工具",
            "效率提升首先来自流程设计，而不是工具数量。",
            quote="先改流程，再换工具。",
        ),
    ]
    knowledge = _knowledge(notes)
    raw_dir = tmp_path / "raw"
    for note in notes:
        document = UnifiedDocument(
            id=note.document_id,
            content_type="idea",
            title=note.title,
            content=note.original_content or note.summary,
            source_type="manual",
        )
        RawStorage(raw_dir).store(document, document.content.encode("utf-8"))
    candidate_result = TopicGenerator(
        index=_index(notes),
        knowledge=[knowledge],
        notes=notes,
        clock=lambda: NOW,
    ).generate()
    candidate = next(
        item for item in candidate_result.candidates if "AI" in item.title
    )
    return notes, knowledge, candidate, raw_dir


def test_unconfirmed_selection_returns_structured_rejection_without_retrieval(tmp_path):
    notes, knowledge, candidate, raw_dir = _fixed_library(tmp_path)

    class CountingRetrieval(RetrievalService):
        def __init__(self, index):
            super().__init__(index=index)
            self.calls = 0

        def search(self, query, *, limit=10):
            self.calls += 1
            return super().search(query, limit=limit)

    retrieval = CountingRetrieval(_index(notes))
    result = ScriptWriter(
        index=_index(notes),
        knowledge=[knowledge],
        notes=notes,
        raw_dir=raw_dir,
        retrieval=retrieval,
    ).write(candidate, confirmed=False)

    assert result.status == "not_confirmed"
    assert result.selection_confirmed is False
    assert result.script is None
    assert "确认" in result.message
    assert retrieval.calls == 0


def test_confirmed_topic_retrieves_again_and_generates_traceable_script(tmp_path):
    notes, knowledge, candidate, raw_dir = _fixed_library(tmp_path)

    class CountingRetrieval(RetrievalService):
        def __init__(self, index):
            super().__init__(index=index)
            self.queries = []

        def search(self, query, *, limit=10):
            self.queries.append(query)
            return super().search(query, limit=limit)

    retrieval = CountingRetrieval(_index(notes))
    provider = MockAIProvider()
    writer = ScriptWriter(
        index=_index(notes),
        knowledge=[knowledge],
        notes=notes,
        raw_dir=raw_dir,
        retrieval=retrieval,
        provider=provider,
    )
    result = writer.write(candidate, confirmed=True)
    second = writer.write(candidate, confirmed=True)

    assert result.status == "generated"
    assert result.selection_confirmed is True
    assert result.selection.confirmed is True
    assert result.title
    assert result.title.startswith("为什么学了很多 AI 还是用不起来")
    assert result.retrieval.status == "ok"
    assert MIN_SCRIPT_CHARS <= len(result.script_text) <= MAX_SCRIPT_CHARS
    assert "AI 工作流" in result.script_text
    assert "把 AI 工具组合成可复用的效率流程" in result.script_text
    assert "先把任务拆成流程，再决定工具。" in result.script_text
    assert result.script_text.startswith("很多人")
    assert not any(
        marker in result.script_text
        for marker in ("来源一", "来源二", "来源三", "Raw", "Note", "Knowledge", "本地检索")
    )
    assert {source.kind for source in result.sources} == {"knowledge", "note", "raw"}
    assert {item.source_kind for item in result.evidence} == {
        "knowledge",
        "note",
        "raw",
    }
    assert provider.calls == ["write_script", "write_script"]
    assert retrieval.queries == [candidate.title, candidate.title]
    assert second.retrieval is not result.retrieval


def test_fallback_script_sanitizes_internal_source_labels(tmp_path):
    notes = [
        _note(
            "internal-labels",
            "AI 视频工作流",
            "来源一 Raw 内容来自 Note，Knowledge 只作内部整理，原始文章字段不应出现。",
        )
    ]
    knowledge = _knowledge(notes)
    raw_dir = tmp_path / "raw"
    document = UnifiedDocument(
        id=notes[0].document_id,
        content_type="idea",
        title=notes[0].title,
        content=notes[0].original_content or notes[0].summary,
        source_type="manual",
    )
    RawStorage(raw_dir).store(document, document.content.encode("utf-8"))
    result = ScriptWriter(
        index=_index(notes),
        knowledge=[knowledge],
        notes=notes,
        raw_dir=raw_dir,
        provider=MockAIProvider(),
    ).write(notes[0].title, confirmed=True)

    assert not any(
        marker.casefold() in result.script_text.casefold()
        for marker in ("来源一", "Raw", "Note", "Knowledge", "原始文章")
    )


def test_provider_copy_without_hook_falls_back_to_publishable_script(tmp_path):
    notes, knowledge, _candidate, raw_dir = _fixed_library(tmp_path)

    class WeakProvider(MockAIProvider):
        def write_script(self, topic, context=(), *, target_seconds=150):
            return "这里是一个没有开头钩子的说明。" * 120

    result = ScriptWriter(
        index=_index(notes),
        knowledge=[knowledge],
        notes=notes,
        raw_dir=raw_dir,
        provider=WeakProvider(),
    ).write(notes[0].title, confirmed=True)

    assert result.script_text.startswith("很多人")
    assert MIN_SCRIPT_CHARS <= len(result.script_text) <= MAX_SCRIPT_CHARS


def test_index_hit_without_readable_evidence_is_explicit(tmp_path):
    note = _note("missing", "AI 工作流资料", "这条 Note 不会被保存。")
    result = ScriptWriter(
        index=_index([note]),
        knowledge_dir=tmp_path / "knowledge",
        notes_dir=tmp_path / "notes",
        raw_dir=tmp_path / "raw",
    ).write("AI 工作流：从工具到流程", confirmed=True)

    assert result.status == "insufficient_evidence"
    assert result.script is None
    assert result.retrieval.status == "ok"
    assert result.note_sources[0].available is False
    assert "证据不足" in result.message


def test_cli_requires_confirm_and_returns_json_result(tmp_path):
    notes, knowledge, candidate, raw_dir = _fixed_library(tmp_path)
    notes_dir = tmp_path / "notes"
    for note in notes:
        NoteStorage(notes_dir).write(note)
    knowledge_dir = tmp_path / "knowledge"
    from pkb.knowledge import KnowledgeStorage

    KnowledgeStorage(knowledge_dir).write(knowledge)
    index_path = tmp_path / "index.json"
    from pkb.index import IndexBuilder

    IndexBuilder(notes_dir, index_path, clock=lambda: NOW).rebuild()

    rejected = runner.invoke(
        app,
        [
            "write-script",
            candidate.title,
            "--index-path",
            str(index_path),
            "--knowledge-dir",
            str(knowledge_dir),
            "--notes-dir",
            str(notes_dir),
            "--raw-dir",
            str(raw_dir),
            "--json",
        ],
    )
    accepted = runner.invoke(
        app,
        [
            "write-script",
            candidate.title,
            "--confirm",
            "--index-path",
            str(index_path),
            "--knowledge-dir",
            str(knowledge_dir),
            "--notes-dir",
            str(notes_dir),
            "--raw-dir",
            str(raw_dir),
            "--json",
        ],
    )

    assert rejected.exit_code == 0, rejected.output
    assert '"status": "not_confirmed"' in rejected.output
    assert '"selection_confirmed": false' in rejected.output
    assert accepted.exit_code == 0, accepted.output
    assert '"status": "generated"' in accepted.output
    assert '"source_kind": "knowledge"' in accepted.output
