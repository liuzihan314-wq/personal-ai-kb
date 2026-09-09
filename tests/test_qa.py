from datetime import datetime, timezone
from pathlib import Path

from pkb.index import IndexBuilder
from pkb.index import IndexEntry, IndexFile
from pkb.knowledge import KnowledgeSource, KnowledgeStorage, TopicKnowledge
from pkb.models import UnifiedDocument
from pkb.notes import Note, NoteStorage
from pkb.providers import MockAIProvider, UnconfiguredProvider
from pkb.qa import QAService
from pkb.storage import RawStorage
from typer.testing import CliRunner

from pkb.cli.main import app


FIXED_TIME = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
runner = CliRunner()


def _note(document_id: str, title: str, summary: str) -> Note:
    return Note(
        document_id=document_id,
        source_type="manual",
        title=title,
        created_at=FIXED_TIME,
        tags=["AI 视频"],
        summary=summary,
        key_points=[f"{title} 的核心做法可被本地知识库追溯。"],
        source_reference=f"raw:{document_id}",
    )


def test_video_question_uses_knowledge_and_traces_back_to_notes(tmp_path):
    notes_dir = tmp_path / "data" / "notes"
    knowledge_dir = tmp_path / "data" / "knowledge"
    index_path = tmp_path / "data" / "index" / "index.json"
    notes = [
        _note("video-1", "AI 视频生成路线", "可以采用文生视频和图生视频两条路线。"),
        _note("video-2", "AI 视频工作流", "也可以通过数字人和自动剪辑提高内容生产效率。"),
    ]
    note_storage = NoteStorage(notes_dir)
    for note in notes:
        note_storage.write(note)

    index = IndexBuilder(notes_dir, index_path, clock=lambda: FIXED_TIME).rebuild()
    knowledge = TopicKnowledge(
        topic="AI 视频",
        created_at=FIXED_TIME,
        updated_at=FIXED_TIME,
        source_note_ids=[note.document_id for note in notes],
        source_references=[note.source_reference for note in notes],
        synthesis="当前主要思路包括文生视频、图生视频、数字人和自动剪辑。",
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
    knowledge_record = KnowledgeStorage(knowledge_dir).write(knowledge)
    before = {
        path: path.read_bytes()
        for path in [*notes_dir.glob("*.md"), index_path, knowledge_record.path]
    }

    provider = MockAIProvider(
        responses={
            "answer_question": "库内资料显示，AI 视频主要有文生视频、图生视频、数字人和自动剪辑。",
        }
    )
    result = QAService(
        index=index,
        knowledge_dir=knowledge_dir,
        notes_dir=notes_dir,
        raw_dir=tmp_path / "data" / "raw",
        provider=provider,
    ).answer("AI 视频有哪些思路？")

    assert result.status == "answered"
    assert result.answer == (
        "库内资料显示，AI 视频主要有文生视频、图生视频、数字人和自动剪辑。"
    )
    assert result.evidence_level == "knowledge+notes"
    assert result.knowledge_topics == ["AI 视频"]
    assert [source.kind for source in result.sources] == [
        "knowledge",
        "note",
        "note",
    ]
    assert result.sources[0].path == str(knowledge_record.path)
    assert {source.source_id for source in result.note_sources} == {"video-1", "video-2"}
    assert all(source.available for source in result.note_sources)
    assert {item.source_kind for item in result.evidence} == {"knowledge", "note"}
    assert provider.calls == ["answer_question"]
    assert before == {
        path: path.read_bytes()
        for path in [*notes_dir.glob("*.md"), index_path, knowledge_record.path]
    }


def _index_entry(document_id: str, title: str, note_path: Path) -> IndexEntry:
    return IndexEntry(
        document_id=document_id,
        title=title,
        source_type="manual",
        note_path=str(note_path),
        keywords=[title],
    )


def test_retrieval_notes_are_used_when_no_matching_knowledge_exists(tmp_path):
    notes_dir = tmp_path / "notes"
    knowledge_dir = tmp_path / "knowledge"
    notes_dir.mkdir()
    note = _note(
        "workflow-1",
        "Agentic coding workflow",
        "Agentic coding can split work into small, traceable tasks.",
    )
    note_storage = NoteStorage(notes_dir)
    note_storage.write(note)
    index = IndexBuilder(notes_dir, clock=lambda: FIXED_TIME).build()
    provider = MockAIProvider(
        responses={"answer_question": "这个结论来自检索到的本地 Note。"}
    )

    result = QAService(
        index=index,
        knowledge_dir=knowledge_dir,
        notes_dir=notes_dir,
        provider=provider,
    ).answer("Agentic coding 怎么拆分工作？")

    assert result.status == "answered"
    assert result.evidence_level == "notes"
    assert result.knowledge_topics == []
    assert [source.source_id for source in result.note_sources] == ["workflow-1"]
    assert result.retrieval.candidates[0].document_id == "workflow-1"
    assert provider.calls == ["answer_question"]


def test_raw_is_used_when_retrieval_note_is_missing(tmp_path):
    notes_dir = tmp_path / "notes"
    raw_dir = tmp_path / "raw"
    missing_note = notes_dir / "raw-only.md"
    document = UnifiedDocument(
        id="raw-only",
        content_type="idea",
        title="AI 视频原始想法",
        content="原始想法：先用图生视频，再用自动剪辑完成短视频。",
        source_type="manual",
    )
    RawStorage(raw_dir).store(document, document.content.encode("utf-8"))
    index = IndexFile(
        notes_dir=str(notes_dir),
        entries=[_index_entry("raw-only", "AI 视频原始想法", missing_note)],
    )
    provider = MockAIProvider(
        responses={"answer_question": "这个回答使用了本地 Raw 原文。"}
    )

    result = QAService(
        index=index,
        knowledge_dir=tmp_path / "knowledge",
        notes_dir=notes_dir,
        raw_dir=raw_dir,
        provider=provider,
    ).answer("AI 视频原始想法是什么？")

    assert result.status == "answered"
    assert result.evidence_level == "raw"
    assert result.note_sources[0].available is False
    assert result.raw_sources[0].path == str(raw_dir / "raw-only" / "original.txt")
    assert result.evidence[-1].source_kind == "raw"
    assert provider.calls == ["answer_question"]


def test_knowledge_source_mapping_selects_distinct_raw_id(tmp_path):
    notes_dir = tmp_path / "notes"
    raw_dir = tmp_path / "raw"
    knowledge_dir = tmp_path / "knowledge"
    note_id = "note-summary"
    raw_id = "raw-original"
    document = UnifiedDocument(
        id=raw_id,
        content_type="idea",
        title="AI 视频原始资料",
        content="Raw 原文说明图生视频适合从已有画面继续创作。",
        source_type="manual",
    )
    RawStorage(raw_dir).store(document, document.content.encode("utf-8"))
    index = IndexFile(
        notes_dir=str(notes_dir),
        entries=[_index_entry(note_id, "AI 视频资料", notes_dir / "missing.md")],
    )
    KnowledgeStorage(knowledge_dir).write(
        TopicKnowledge(
            topic="AI 视频",
            created_at=FIXED_TIME,
            updated_at=FIXED_TIME,
            source_note_ids=[note_id],
            source_references=[f"raw:{raw_id}"],
            synthesis="主题综合记录了图生视频路线。",
            sources=[
                KnowledgeSource(
                    note_id=note_id,
                    title="AI 视频资料",
                    raw_document_id=raw_id,
                    reference=f"raw:{raw_id}",
                )
            ],
        )
    )

    result = QAService(
        index=index,
        knowledge_dir=knowledge_dir,
        notes_dir=notes_dir,
        raw_dir=raw_dir,
        provider=MockAIProvider(
            responses={"answer_question": "基于主题与 Raw 原文回答。"}
        ),
    ).answer("AI 视频有哪些思路？")

    assert result.status == "answered"
    assert result.evidence_level == "knowledge+raw"
    assert result.raw_sources[0].source_id == raw_id
    assert result.raw_sources[0].path == str(raw_dir / raw_id / "original.txt")


def test_no_hits_is_structured_and_does_not_call_provider(tmp_path):
    provider = MockAIProvider(
        responses={"answer_question": "这段内容不应该被调用。"}
    )
    index = IndexFile(
        notes_dir=str(tmp_path / "notes"),
        entries=[
            _index_entry(
                "bread",
                "面包烘焙",
                tmp_path / "notes" / "bread.md",
            )
        ],
    )

    result = QAService(
        index=index,
        knowledge_dir=tmp_path / "knowledge",
        notes_dir=tmp_path / "notes",
        raw_dir=tmp_path / "raw",
        provider=provider,
    ).answer("我收藏过哪些数据库迁移资料？")

    assert result.status == "no_hits"
    assert result.answer is None
    assert result.sources == []
    assert result.evidence == []
    assert result.reason
    assert provider.calls == []


def test_index_hit_without_readable_content_is_insufficient_evidence(tmp_path):
    provider = MockAIProvider()
    index = IndexFile(
        notes_dir=str(tmp_path / "notes"),
        entries=[
            _index_entry(
                "missing",
                "本地 Agent 工作流",
                tmp_path / "notes" / "missing.md",
            )
        ],
    )

    result = QAService(
        index=index,
        knowledge_dir=tmp_path / "knowledge",
        notes_dir=tmp_path / "notes",
        raw_dir=tmp_path / "raw",
        provider=provider,
    ).answer("Agent 工作流有哪些内容？")

    assert result.status == "insufficient_evidence"
    assert result.answer is None
    assert result.retrieval.status == "ok"
    assert result.note_sources[0].available is False
    assert provider.calls == []


def test_unconfigured_provider_returns_evidence_without_a_fake_answer(tmp_path):
    notes_dir = tmp_path / "notes"
    knowledge_dir = tmp_path / "knowledge"
    note = _note("video-1", "AI 视频工具", "文生视频、图生视频和剪辑工具各有用途。")
    NoteStorage(notes_dir).write(note)
    index = IndexBuilder(notes_dir, clock=lambda: FIXED_TIME).build()

    result = QAService(
        index=index,
        knowledge_dir=knowledge_dir,
        notes_dir=notes_dir,
        provider=UnconfiguredProvider(),
    ).answer("AI 视频制作有哪些工具？")

    assert result.status == "provider_not_configured"
    assert result.answer is None
    assert result.sources
    assert "未配置 AI Provider" in result.reason


def test_cli_ask_returns_traceable_json(tmp_path):
    notes_dir = tmp_path / "notes"
    knowledge_dir = tmp_path / "knowledge"
    index_path = tmp_path / "index.json"
    note = _note("cli-video", "AI 视频路线", "文生视频和图生视频都可以用于内容创作。")
    NoteStorage(notes_dir).write(note)
    IndexBuilder(notes_dir, index_path, clock=lambda: FIXED_TIME).rebuild()
    KnowledgeStorage(knowledge_dir).write(
        TopicKnowledge(
            topic="AI 视频",
            created_at=FIXED_TIME,
            updated_at=FIXED_TIME,
            source_note_ids=[note.document_id],
            source_references=[note.source_reference],
            synthesis="AI 视频可以采用文生视频和图生视频。",
            sources=[
                KnowledgeSource(
                    note_id=note.document_id,
                    title=note.title,
                    raw_document_id=note.document_id,
                    reference=note.source_reference,
                )
            ],
        )
    )

    result = runner.invoke(
        app,
        [
            "ask",
            "AI 视频有哪些思路？",
            "--index-path",
            str(index_path),
            "--knowledge-dir",
            str(knowledge_dir),
            "--notes-dir",
            str(notes_dir),
            "--raw-dir",
            str(tmp_path / "raw"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert '"status": "answered"' in result.output
    assert '"kind": "knowledge"' in result.output
    assert '"source_id": "cli-video"' in result.output
