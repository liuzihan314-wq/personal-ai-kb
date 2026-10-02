from datetime import datetime, timezone
import pytest

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


def test_confirmed_topic_retrieves_again_and_generates_traceable_script(tmp_path, spoken_copy):
    notes, knowledge, candidate, raw_dir = _fixed_library(tmp_path)

    class CountingRetrieval(RetrievalService):
        def __init__(self, index):
            super().__init__(index=index)
            self.queries = []

        def search(self, query, *, limit=10):
            self.queries.append(query)
            return super().search(query, limit=limit)

    retrieval = CountingRetrieval(_index(notes))
    provider = MockAIProvider({"write_script": spoken_copy})
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
    assert result.title == candidate.title
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
    assert provider.calls == ["write_script", "plan_visual_materials", "plan_visual_materials", "write_script", "plan_visual_materials", "plan_visual_materials"]
    assert retrieval.queries == [candidate.title, candidate.title]
    assert second.retrieval is not result.retrieval


def test_internal_source_labels_fail_quality_gate_without_a_template(tmp_path):
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

    assert result.status == "quality_failed"
    assert result.script is None


def test_provider_copy_without_hook_is_rejected_after_one_rewrite(tmp_path):
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

    assert result.status == "quality_failed"
    assert result.script is None
    assert "开头" in result.message


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


def test_invalid_draft_receives_specific_feedback_and_can_be_rewritten(tmp_path, spoken_copy):
    notes, knowledge, candidate, raw_dir = _fixed_library(tmp_path)

    class RepairingProvider(MockAIProvider):
        def __init__(self):
            super().__init__()
            self.requests = []

        def write_script(self, topic, context=(), *, target_seconds=150):
            self.requests.append(topic)
            return "本文是AI学习之路第20篇。" if len(self.requests) == 1 else spoken_copy

    provider = RepairingProvider()
    result = ScriptWriter(index=_index(notes), knowledge=[knowledge], notes=notes, raw_dir=raw_dir, provider=provider).write(candidate, confirmed=True)
    assert result.status == "generated" and result.script == spoken_copy
    assert len(provider.requests) == 2
    assert "编辑修订要求" in provider.requests[1] and "文章介绍" in provider.requests[1]
    assert result.title == candidate.title


def test_script_provider_error_is_not_replaced_with_a_draft(tmp_path):
    from pkb.scripts import ScriptProviderError

    notes, knowledge, candidate, raw_dir = _fixed_library(tmp_path)

    class BrokenProvider(MockAIProvider):
        attempts = 0

        def write_script(self, topic, context=(), *, target_seconds=150):
            self.attempts += 1
            raise RuntimeError("synthetic upstream failure")

    provider = BrokenProvider()
    with pytest.raises(ScriptProviderError):
        ScriptWriter(index=_index(notes), knowledge=[knowledge], notes=notes, raw_dir=raw_dir, provider=provider).write(candidate, confirmed=True)
    assert provider.attempts == 1


def _visual_items():
    return [dict(paragraph=i, visual=f"展示第 {i} 步的输入与输出对比", preparation=["打开当前 AI 网页，输入稿件中的同一个主题。", "录下补充背景后的操作与真实结果，不预设结果。"], tool="当前 AI 网页＋系统录屏", alternative="用操作截图和字幕标出变化。") for i in range(1, 4)]


def test_accepted_script_gets_separate_actionable_materials(tmp_path, spoken_copy):
    notes, knowledge, candidate, raw_dir = _fixed_library(tmp_path)
    provider = MockAIProvider({"write_script": spoken_copy, "plan_visual_materials": _visual_items()})
    result = ScriptWriter(index=_index(notes), knowledge=[knowledge], notes=notes, raw_dir=raw_dir, provider=provider).write(candidate, confirmed=True)
    assert result.status == "generated" and result.script == spoken_copy
    assert len(result.visual_materials) == 3
    assert all(item.preparation and item.alternative and item.tool for item in result.visual_materials)
    assert "需补录或制作" in result.visual_materials_message
    assert "已有资料仅可作为内容参考" in result.visual_materials_message
    assert "展示第" not in result.script_text
    assert result.model_dump(mode="json")["visual_materials"][0]["paragraph"] == 1


def test_material_planning_retries_without_regenerating_accepted_script(tmp_path, spoken_copy):
    notes, knowledge, candidate, raw_dir = _fixed_library(tmp_path)

    class TransientProvider(MockAIProvider):
        def __init__(self):
            super().__init__({"write_script": spoken_copy})
            self.material_attempts = 0

        def plan_visual_materials(self, topic, paragraphs):
            self.material_attempts += 1
            if self.material_attempts == 1:
                raise ValueError("temporary malformed response")
            return _visual_items()

    provider = TransientProvider()
    result = ScriptWriter(index=_index(notes), knowledge=[knowledge], notes=notes, raw_dir=raw_dir, provider=provider).write(candidate, confirmed=True)
    assert result.status == "generated" and result.script == spoken_copy
    assert len(result.visual_materials) == 3
    assert provider.material_attempts == 2
    assert provider.calls == ["write_script"]


@pytest.mark.parametrize("failure", ["count", "paragraph", "step", "duplicate", "upstream"])
def test_invalid_materials_preserve_the_accepted_script(tmp_path, spoken_copy, failure):
    notes, knowledge, candidate, raw_dir = _fixed_library(tmp_path)
    items = _visual_items()
    if failure == "count":
        items = items[:1]
    elif failure == "paragraph":
        items[0]["paragraph"] = 999
    elif failure == "step":
        items[0]["preparation"] = [" "]
    elif failure == "duplicate":
        items[1]["visual"] = items[0]["visual"]

    class Provider(MockAIProvider):
        def plan_visual_materials(self, topic, paragraphs):
            assert paragraphs[0] == spoken_copy.split("\n\n")[0]
            if failure == "upstream":
                raise RuntimeError("synthetic failure")
            return items

    result = ScriptWriter(index=_index(notes), knowledge=[knowledge], notes=notes, raw_dir=raw_dir, provider=Provider({"write_script": spoken_copy})).write(candidate, confirmed=True)
    assert result.status == "generated" and result.script == spoken_copy
    assert result.visual_materials == []
    assert "合格口播稿已保留" in result.visual_materials_message


def test_focused_candidate_excludes_unrelated_notes_and_broad_knowledge(tmp_path):
    notes, knowledge, candidate, raw_dir = _fixed_library(tmp_path)
    candidate = candidate.model_copy(update={"focus": "流程", "sources": [source for source in candidate.sources if source.kind == "note" and source.source_id == "workflow-1"]})

    class CapturingProvider(MockAIProvider):
        def __init__(self):
            super().__init__()
            self.contexts = []

        def write_script(self, topic, context=(), *, target_seconds=150):
            self.contexts.append(context)
            return "不够长的稿件"

    provider = CapturingProvider()
    result = ScriptWriter(index=_index(notes), knowledge=[knowledge], notes=notes, raw_dir=raw_dir, provider=provider).write(candidate, confirmed=True)
    assert result.status == "quality_failed"
    assert result.retrieval.query == "流程"
    assert {item.document_id for item in result.retrieval.candidates} == {"workflow-1"}
    assert len(provider.contexts) == 2
    assert all(item.document_id == "workflow-1" for context in provider.contexts for item in context)
    assert {source.kind for source in result.sources} == {"note", "raw"}
    assert result.retrieval.status == "ok"


def test_cli_requires_confirm_and_returns_json_result(tmp_path, monkeypatch, spoken_copy):
    monkeypatch.setattr("pkb.scripts.service.configured_provider", lambda _settings: MockAIProvider({"write_script": spoken_copy}))
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
