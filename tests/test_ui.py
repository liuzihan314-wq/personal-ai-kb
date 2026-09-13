from datetime import datetime, timezone
from pathlib import Path

import pymupdf

from pkb.index import IndexBuilder, IndexEntry, IndexFile, write_index
from pkb.knowledge import KnowledgeSource, KnowledgeStorage, TopicKnowledge
from pkb.models import UnifiedDocument
from pkb.notes import Note, NoteStorage
from pkb.providers import MockAIProvider, OpenAICompatibleProvider
from pkb.storage import RawStorage
from pkb.retrieval import DashScopeEmbeddingClient
from pkb.topics import TopicCandidate, TopicEvidence, TopicReason, TopicSource
from pkb.ui import UIPaths, UIService, can_generate_script


NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def _make_pdf(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    payload = document.tobytes()
    document.close()
    return payload


def _seed_script_library(data_dir: Path) -> TopicCandidate:
    paths = UIPaths.from_data_dir(data_dir)
    note_storage = NoteStorage(paths.notes_dir)
    raw_storage = RawStorage(paths.raw_dir)
    notes: list[Note] = []
    for document_id, title, summary in (
        ("workflow-1", "AI 工作流：从工具到流程", "把 AI 工具组合成可复用的效率流程。"),
        ("workflow-2", "AI 工作流：自动化减少重复劳动", "自动化要嵌入工作流，先验证具体任务的收益。"),
        ("workflow-3", "AI 工作流：先改流程再换工具", "效率提升首先来自流程设计，而不是工具数量。"),
    ):
        note = Note(
            document_id=document_id,
            source_type="manual",
            title=title,
            content_type="idea",
            tags=["AI", "workflow"],
            summary=summary,
            key_points=[f"把“{title}”拆成可验证的具体步骤。"],
            quotes=["先把任务拆成流程，再决定工具。"],
            original_content=summary,
            source_reference=f"raw:{document_id}",
        )
        notes.append(note)
        note_storage.write(note)
        raw_storage.store(
            UnifiedDocument(
                id=document_id,
                content_type="idea",
                title=title,
                content=summary,
                source_type="manual",
            ),
            summary.encode("utf-8"),
        )

    index = IndexBuilder(paths.notes_dir, paths.index_path).rebuild()
    KnowledgeStorage(paths.knowledge_dir).write(
        TopicKnowledge(
            topic="AI 工作流",
            created_at=NOW,
            updated_at=NOW,
            source_note_ids=[note.document_id for note in notes],
            source_references=[note.source_reference for note in notes],
            synthesis="把 AI 工具放进可复用的工作流，并用结果验证取舍。",
            sources=[
                KnowledgeSource(
                    note_id=note.document_id,
                    raw_document_id=note.document_id,
                    title=note.title,
                    reference=note.source_reference,
                )
                for note in notes
            ],
        ),
    )
    note_sources = [
        TopicSource(
            kind="note",
            source_id=note.document_id,
            title=note.title,
            path=str(next(entry.note_path for entry in index.entries if entry.document_id == note.document_id)),
            reference=note.source_reference,
            content_type=note.content_type,
        )
        for note in notes
    ]
    return TopicCandidate(
        title="AI 工作流",
        why_worth_doing="三条本地材料都指向可复用的 AI 工作流。",
        score=0.8,
        sources=note_sources,
        evidence=[
            TopicEvidence(
                signal="tag",
                values=["AI", "workflow"],
                source_ids=[note.document_id for note in notes],
                explanation="共同标签形成主题交集。",
            ),
            TopicEvidence(
                signal="title",
                values=[note.title for note in notes],
                source_ids=[note.document_id for note in notes],
                explanation="标题都保留了 AI 工作流方向。",
            ),
        ],
        reasons=[
            TopicReason(
                rule="local_overlap",
                matches=[note.document_id for note in notes],
                weight=0.8,
                explanation="多个本地来源有稳定重合信号。",
            ),
        ],
    )


def test_ui_paths_follow_the_project_data_contract(tmp_path):
    paths = UIPaths.from_data_dir(tmp_path)

    assert paths.raw_dir == tmp_path / "raw"
    assert paths.notes_dir == tmp_path / "notes"
    assert paths.knowledge_dir == tmp_path / "knowledge"
    assert paths.index_path == tmp_path / "index" / "index.json"


def test_ui_service_can_use_a_browser_session_provider_without_persisting_a_key(tmp_path):
    service = UIService.with_session_provider(
        UIPaths.from_data_dir(tmp_path),
        provider_name="deepseek",
        model="session-model",
        base_url="https://api.example.test/v1",
        api_key="session-only-key",
    )

    assert isinstance(service.provider, OpenAICompatibleProvider)
    assert service.provider.model == "session-model"


def test_ui_can_enable_embedding_without_replacing_chat_provider(tmp_path):
    service = UIService.with_session_embedding(
        UIPaths.from_data_dir(tmp_path),
        embedding_model="qwen3.7-text-embedding-flash",
        embedding_base_url="https://workspace.example.test/compatible-mode/v1",
        embedding_api_key="embedding-session-key",
        provider=MockAIProvider(),
    )

    assert isinstance(service.provider, MockAIProvider)
    assert isinstance(service.embedding_client, DashScopeEmbeddingClient)


def test_ui_session_bindings_cover_all_combinations_and_clear_independently(tmp_path):
    from pkb.ui.app import _service_for_session_values

    default = UIService(UIPaths.from_data_dir(tmp_path), provider=MockAIProvider())
    provider_values = {
        "provider_name": "deepseek",
        "model": "session-model",
        "base_url": "https://api.example.test/v1",
        "api_key": "session-only-key",
    }
    embedding_values = {
        "embedding_model": "qwen3.7-text-embedding-flash",
        "embedding_base_url": "https://workspace.example.test/compatible-mode/v1",
        "embedding_api_key": "embedding-session-key",
    }

    assert _service_for_session_values(default, None, None) is default
    provider_only = _service_for_session_values(default, provider_values, None)
    assert provider_only.embedding_client is None
    embedding_only = _service_for_session_values(default, None, embedding_values)
    assert embedding_only.provider is default.provider
    assert embedding_only.embedding_client is not None
    both = _service_for_session_values(default, provider_values, embedding_values)
    assert both.embedding_client is not None
    assert both.provider.model == "session-model"

    state = {
        "provider_session": provider_values,
        "embedding_session": embedding_values,
    }
    state["provider_session"] = None
    assert state["embedding_session"] == embedding_values
    state["embedding_session"] = None
    assert state["provider_session"] is None


def test_ui_session_embedding_configuration_is_passed_to_search_and_qa(
    tmp_path,
    monkeypatch,
):
    service = UIService.with_session_provider(
        UIPaths.from_data_dir(tmp_path),
        provider_name="deepseek",
        model="session-model",
        base_url="https://api.example.test/v1",
        api_key="session-only-key",
        embedding_model="qwen3.7-text-embedding-flash",
        embedding_base_url="https://workspace.example.test/compatible-mode/v1",
        embedding_api_key="embedding-session-key",
    )

    assert isinstance(service.embedding_client, DashScopeEmbeddingClient)
    assert service.embedding_client.model == "qwen3.7-text-embedding-flash"

    captured = {}

    class FakeRetrievalService:
        def __init__(self, _index_path):
            pass

        def search(self, _query, *, limit, embedding_client):
            captured["search"] = embedding_client
            return None

    class FakeQAService:
        def __init__(self, **kwargs):
            captured["qa"] = kwargs["embedding_client"]

        def answer(self, _question, *, limit):
            return None

    monkeypatch.setattr("pkb.ui.services.RetrievalService", FakeRetrievalService)
    monkeypatch.setattr("pkb.ui.services.QAService", FakeQAService)

    service.search("动作自然")
    service.answer("动作自然")

    assert captured == {
        "search": service.embedding_client,
        "qa": service.embedding_client,
    }


def test_ui_without_embedding_configuration_does_not_make_network_requests(
    tmp_path,
    monkeypatch,
):
    index_path = UIPaths.from_data_dir(tmp_path).index_path
    write_index(
        index_path,
        IndexFile(
            notes_dir=str(tmp_path / "notes"),
            entries=[
                IndexEntry(
                    document_id="one",
                    title="AI 工作流",
                    source_type="manual",
                    note_path=str(tmp_path / "notes" / "one.md"),
                ),
            ],
        ),
    )
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("PKB_EMBEDDING_BASE_URL", raising=False)
    monkeypatch.setattr(
        DashScopeEmbeddingClient,
        "from_environment",
        lambda: (_ for _ in ()).throw(AssertionError("environment client must not be used")),
    )

    service = UIService(UIPaths.from_data_dir(tmp_path))
    result = service.search("AI")
    qa_result = service.answer("AI")

    assert result.found
    assert qa_result.status == "insufficient_evidence"


def test_pdf_import_runs_the_minimal_persisted_ui_slice(tmp_path):
    service = UIService(
        UIPaths.from_data_dir(tmp_path),
        provider=MockAIProvider(),
    )

    result = service.import_pdf("workflow.pdf", _make_pdf("AI 工作流需要先拆解任务。"))

    assert result.document.content_type == "pdf"
    assert result.note.note.document_id == result.document.id
    assert result.note.path.is_file()
    assert result.index.entries[0].document_id == result.document.id
    assert UIService(UIPaths.from_data_dir(tmp_path)).search("AI").found


def test_successful_ingest_invalidates_results_from_the_previous_index():
    from pkb.ui.app import _invalidate_results_after_ingest

    state = {
        "search_result": object(),
        "qa_result": object(),
        "knowledge_result": object(),
        "topics_result": object(),
        "script_result": object(),
        "topic_widget_previous": "旧选题",
        "topic_selection_confirmed": True,
        "provider_session": {"api_key": "session-only"},
        "last_ingest": object(),
    }

    _invalidate_results_after_ingest(state)

    assert all(state[key] is None for key in (
        "search_result",
        "qa_result",
        "knowledge_result",
        "topics_result",
        "script_result",
        "topic_widget_previous",
    ))
    assert state["topic_selection_confirmed"] is False
    assert state["provider_session"] == {"api_key": "session-only"}
    assert state["last_ingest"] is not None


def test_idea_card_updates_note_and_index_without_reimplementing_storage(tmp_path):
    service = UIService(
        UIPaths.from_data_dir(tmp_path),
        provider=MockAIProvider(),
    )

    result = service.add_idea(
        "先改流程，再换工具。",
        source_url="https://example.test/idea",
        tags=["AI", "workflow"],
    )

    assert result.document.content_type == "idea"
    assert result.document.tags == ["AI", "workflow"]
    assert result.note.note.original_content == result.document.content
    assert result.index.entries[0].document_id == result.document.id


def test_unconfirmed_topic_cannot_enable_or_generate_script(tmp_path):
    provider = MockAIProvider()
    service = UIService(UIPaths.from_data_dir(tmp_path), provider=provider)

    result = service.write_script(None, confirmed=False)

    assert not can_generate_script([], None, confirmed=False)
    assert result.status == "not_confirmed"
    assert result.script is None
    assert provider.calls == []


def test_topic_gate_requires_selection_then_explicit_confirmation(tmp_path):
    from pkb.ui.app import _html, _topic_gate_state

    candidate = _seed_script_library(tmp_path)

    status, message, allowed = _topic_gate_state([], None, confirmed=False)
    assert status == "待选择"
    assert "选择" in message
    assert allowed is False

    status, message, allowed = _topic_gate_state(
        [candidate],
        candidate.title,
        confirmed=False,
    )
    assert status == "待确认"
    assert "确认" in message
    assert allowed is False

    status, message, allowed = _topic_gate_state(
        [candidate],
        candidate.title,
        confirmed=True,
    )
    assert status == "已确认"
    assert "生成口播" in message
    assert allowed is True
    assert _html('<unsafe & "value">') == "&lt;unsafe &amp; &quot;value&quot;&gt;"


def test_confirmed_candidate_uses_script_writer_retrieval_and_source_chain(tmp_path):
    candidate = _seed_script_library(tmp_path)
    provider = MockAIProvider()
    service = UIService(UIPaths.from_data_dir(tmp_path), provider=provider)

    assert can_generate_script([candidate], candidate.title, confirmed=True)
    result = service.write_script(candidate, confirmed=True)

    assert result.status == "generated"
    assert result.selection_confirmed is True
    assert result.retrieval.query == candidate.title
    assert result.retrieval.candidates
    assert {source.kind for source in result.sources} == {"knowledge", "note", "raw"}
    assert result.evidence
    assert "write_script" in provider.calls


def test_topic_synthesis_and_qa_use_the_existing_core_services(tmp_path):
    _seed_script_library(tmp_path)
    service = UIService(
        UIPaths.from_data_dir(tmp_path),
        provider=MockAIProvider(),
    )

    knowledge = service.synthesize_topic("AI 工作流")
    topics = service.generate_topics()
    answer = service.answer("AI", limit=3)

    assert knowledge.path.is_file()
    assert knowledge.knowledge.source_note_ids
    assert topics.candidates
    assert answer.status == "answered"
    assert answer.sources


def test_streamlit_entrypoint_module_is_importable():
    from pkb.ui import app

    assert callable(app.main)
