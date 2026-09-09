from datetime import datetime, timedelta, timezone

from pkb.index import IndexEntry, IndexFile
from pkb.knowledge import KnowledgeSource, TopicKnowledge
from pkb.notes import Note
from pkb.topics import TopicCandidate, TopicGenerator, generate_topics


NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def _note(
    document_id: str,
    title: str,
    *,
    created_at: datetime,
    content_type: str = "article",
    tags: list[str],
    summary: str,
    quotes: list[str] | None = None,
    original_content: str | None = None,
) -> Note:
    return Note(
        document_id=document_id,
        source_type="manual",
        title=title,
        created_at=created_at,
        content_type=content_type,
        tags=tags,
        summary=summary,
        key_points=[f"{title} provides an actionable workflow."],
        quotes=quotes or [],
        original_content=original_content,
        source_reference=f"raw:{document_id}",
    )


def _index(notes: list[Note]) -> IndexFile:
    return IndexFile(
        notes_dir="data/notes",
        entries=[
            IndexEntry(
                document_id=note.document_id,
                title=note.title,
                created_at=note.created_at,
                content_type=note.content_type,
                tags=note.tags,
                keywords=["AI", "workflow", "效率"],
                source_type=note.source_type,
                note_path=f"data/notes/{note.document_id}.md",
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


def test_fixed_small_library_generates_traceable_candidates_and_uses_idea_card():
    notes = [
        _note(
            "article-1",
            "AI 工作流：从工具到流程",
            created_at=NOW - timedelta(days=5),
            tags=["AI", "workflow"],
            summary="把 AI 工具组合成可复用的效率流程。",
        ),
        _note(
            "article-2",
            "自动化如何减少重复劳动",
            created_at=NOW - timedelta(days=70),
            tags=["workflow", "automation"],
            summary="自动化要嵌入工作流，先验证具体任务的收益。",
        ),
        _note(
            "idea-1",
            "先改流程，再换工具",
            created_at=NOW - timedelta(days=2),
            content_type="idea",
            tags=["AI", "workflow"],
            summary="个人观点卡片：效率提升首先来自流程设计。",
            quotes=["先改流程，再换工具。"],
            original_content="不要迷信新工具，先把重复任务拆成流程。",
        ),
    ]
    index = _index(notes)

    result = generate_topics(
        index=index,
        knowledge=[_knowledge(notes)],
        notes=notes,
        clock=lambda: NOW,
    )

    assert result.status == "ok"
    assert 3 <= len(result.candidates) <= 5
    assert all(isinstance(candidate, TopicCandidate) for candidate in result.candidates)
    assert len({candidate.title for candidate in result.candidates}) == len(result.candidates)
    assert all(candidate.why_worth_doing for candidate in result.candidates)
    assert all(candidate.sources for candidate in result.candidates)
    assert all(source.source_id and source.path for candidate in result.candidates for source in candidate.sources)
    assert all(
        any(source.source_id in {note.document_id for note in notes} for source in candidate.sources)
        for candidate in result.candidates
    )
    assert any(
        evidence.signal == "idea_card"
        for candidate in result.candidates
        for evidence in candidate.evidence
    )
    assert any(
        reason.rule == "recent_material"
        for candidate in result.candidates
        for reason in candidate.reasons
    )
    assert all(
        candidate.title not in {note.title for note in notes}
        for candidate in result.candidates
    )


def test_topic_generation_order_is_stable_when_input_order_changes():
    notes = [
        _note(
            "one",
            "AI workflow basics",
            created_at=NOW - timedelta(days=4),
            tags=["AI", "workflow"],
            summary="AI workflow basics.",
        ),
        _note(
            "two",
            "Workflow automation",
            created_at=NOW - timedelta(days=40),
            tags=["workflow", "automation"],
            summary="Workflow automation for repeated tasks.",
        ),
        _note(
            "three",
            "AI efficiency practice",
            created_at=NOW - timedelta(days=80),
            tags=["AI", "efficiency"],
            summary="Practical AI efficiency improvements.",
        ),
    ]
    knowledge = _knowledge(notes)
    first = generate_topics(
        index=_index(notes),
        knowledge=[knowledge],
        notes=notes,
        clock=lambda: NOW,
    )
    reversed_result = generate_topics(
        index=_index(list(reversed(notes))),
        knowledge=[knowledge],
        notes=list(reversed(notes)),
        clock=lambda: NOW,
    )

    assert [candidate.title for candidate in first.candidates] == [
        candidate.title for candidate in reversed_result.candidates
    ]
    assert [candidate.score for candidate in first.candidates] == [
        candidate.score for candidate in reversed_result.candidates
    ]


def test_semantic_duplicate_knowledge_uses_the_latest_page_without_failing():
    notes = [
        _note(
            "one",
            "AI 视频工具路线",
            created_at=NOW - timedelta(days=4),
            tags=["AI", "视频"],
            summary="文生视频和图生视频都需要先验证工作流。",
        ),
        _note(
            "two",
            "AI 视频制作流程",
            created_at=NOW - timedelta(days=3),
            tags=["AI", "视频"],
            summary="工具选择要围绕脚本、生成和剪辑流程。",
        ),
    ]
    older = _knowledge(notes).model_copy(
        update={"topic": "ai视频", "updated_at": NOW - timedelta(minutes=1)}
    )
    newer = _knowledge(notes).model_copy(
        update={"topic": "ai 视频", "updated_at": NOW}
    )

    result = generate_topics(
        index=_index(notes),
        knowledge=[older, newer],
        notes=notes,
        clock=lambda: NOW,
    )

    assert result.candidates
    knowledge_sources = [
        source
        for candidate in result.candidates
        for source in candidate.sources
        if source.kind == "knowledge"
    ]
    assert knowledge_sources
    assert {source.title for source in knowledge_sources} == {"ai 视频"}


def test_recent_material_has_explicit_moderate_bonus():
    old = _note(
        "old",
        "Local workflow",
        created_at=NOW - timedelta(days=90),
        tags=["workflow"],
        summary="A local workflow for repeated tasks.",
    )
    recent = _note(
        "recent",
        "Local workflow",
        created_at=NOW - timedelta(days=3),
        tags=["workflow"],
        summary="A local workflow for repeated tasks.",
    )
    index = _index([old, recent])
    result = TopicGenerator(index=index, notes=[old, recent], clock=lambda: NOW).generate()

    workflow = next(candidate for candidate in result.candidates if "workflow" in candidate.title.lower())
    recent_reason = next(reason for reason in workflow.reasons if reason.rule == "recent_material")
    assert recent_reason.weight > 0
    assert recent_reason.weight <= 0.1
    assert "30" in recent_reason.explanation


def test_insufficient_material_is_explicit_and_does_not_invent_candidates():
    note = _note(
        "only-one",
        "One local idea",
        created_at=NOW,
        content_type="idea",
        tags=["single"],
        summary="Only one local source is available.",
        original_content="Only one source.",
    )

    result = generate_topics(index=_index([note]), notes=[note], clock=lambda: NOW)

    assert result.status == "insufficient_data"
    assert len(result.candidates) < 3
    assert "不足" in result.message
    assert "虚构" in result.message
