from typer.testing import CliRunner

from pkb.cli.main import app
from pkb.index import (
    IndexEntry,
    IndexFile,
    RelatedEntry,
    RelatedReason,
    write_index,
)
from pkb.retrieval import (
    CandidateJudgmentRequest,
    RetrievalService,
    retrieve_from_index,
)


runner = CliRunner()


def _entry(
    document_id: str,
    title: str,
    *,
    tags: list[str] | None = None,
    keywords: list[str] | None = None,
    topic: str | None = None,
    note_path: str | None = None,
    related: list[RelatedEntry] | None = None,
) -> IndexEntry:
    return IndexEntry(
        document_id=document_id,
        title=title,
        tags=tags or [],
        keywords=keywords or [],
        source_type="manual",
        note_path=note_path or f"notes/{document_id}.md",
        topic=topic,
        related=related or [],
    )


def _index(*entries: IndexEntry) -> IndexFile:
    return IndexFile(notes_dir="notes", entries=list(entries))


def _link(document_id: str, *, score: float = 0.8) -> RelatedEntry:
    return RelatedEntry(
        document_id=document_id,
        score=score,
        reason="shared tags: retrieval",
        reasons=[
            RelatedReason(
                rule="shared_tags",
                matches=["retrieval"],
                weight=score,
            ),
        ],
    )


def test_retrieval_ranks_title_above_weaker_evidence_and_traces_sources():
    index = _index(
        _entry(
            "title-hit",
            "Retrieval workflow",
            keywords=["workflow"],
            note_path="data/notes/title-hit.md",
        ),
        _entry(
            "keyword-hit",
            "Local rules",
            keywords=["retrieval"],
            note_path="data/notes/keyword-hit.md",
        ),
        _entry(
            "unrelated",
            "Bread baking",
            tags=["cooking"],
            keywords=["oven"],
        ),
    )

    result = retrieve_from_index(index, "retrieval")

    assert result.status == "ok"
    assert [candidate.document_id for candidate in result.candidates] == [
        "title-hit",
        "keyword-hit",
    ]
    first = result.candidates[0]
    assert first.score > result.candidates[1].score
    assert first.raw_document_id == "title-hit"
    assert first.note_path == "data/notes/title-hit.md"
    assert first.evidence.title == ["Retrieval workflow"]
    assert first.reasons[0].field == "title"
    assert "retrieval" in first.reasons[0].explanation


def test_tags_keywords_topic_and_existing_related_are_searchable():
    related_target = _entry(
        "target",
        "Agent workflow",
        keywords=["automation"],
    )
    related_only = _entry(
        "related-only",
        "Local links",
        related=[_link("target")],
    )
    index = _index(
        _entry("tag-hit", "Local rules", tags=["agent"]),
        _entry("keyword-hit", "Local rules", keywords=["agent"]),
        _entry("topic-hit", "Local rules", topic="agent systems"),
        related_target,
        related_only,
    )

    for document_id, field in (
        ("tag-hit", "tags"),
        ("keyword-hit", "keywords"),
        ("topic-hit", "topic"),
    ):
        result = retrieve_from_index(index, "agent")
        candidate = next(item for item in result.candidates if item.document_id == document_id)
        assert field in candidate.evidence.matched_fields

    related_candidate = next(
        item
        for item in retrieve_from_index(index, "agent").candidates
        if item.document_id == "related-only"
    )
    assert related_candidate.evidence.related == ["target"]
    assert related_candidate.reasons[-1].field == "related"
    assert "target" in related_candidate.reasons[-1].explanation


def test_empty_topic_is_safe_and_no_match_is_explicit():
    result = retrieve_from_index(
        _index(_entry("empty-topic", "Unrelated title", topic=None)),
        "does-not-exist",
    )

    assert result.status == "no_hits"
    assert result.candidates == []
    assert result.is_empty


def test_service_reads_index_and_prepares_ai_boundary_without_provider(tmp_path):
    index_path = tmp_path / "index.json"
    write_index(
        index_path,
        _index(
            _entry(
                "one",
                "Retrieval notes",
                tags=["local"],
                note_path=str(tmp_path / "notes" / "one.md"),
            ),
        ),
    )
    before = index_path.read_bytes()

    service = RetrievalService(index_path)
    request = service.build_candidate_judgment_request("retrieval")

    assert isinstance(request, CandidateJudgmentRequest)
    assert request.query == "retrieval"
    assert request.candidates[0].raw_document_id == "one"
    assert index_path.read_bytes() == before


def test_search_cli_can_read_synthetic_index_and_report_no_hits(tmp_path):
    index_path = tmp_path / "index.json"
    write_index(index_path, _index(_entry("one", "Retrieval notes")))

    hit = runner.invoke(app, ["search", "retrieval", "--index-path", str(index_path), "--json"])
    assert hit.exit_code == 0, hit.output
    assert '"status": "ok"' in hit.output
    assert '"raw_document_id": "one"' in hit.output

    miss = runner.invoke(app, ["search", "unknown", "--index-path", str(index_path)])
    assert miss.exit_code == 0, miss.output
    assert "status: no_hits" in miss.output
    assert "candidates: 0" in miss.output


def test_dense_related_links_do_not_overrule_direct_video_matches():
    videos = [
        _entry(f"video-{i}", f"AI 视频制作 {i}", keywords=["ai", "视频"])
        for i in range(5)
    ]
    configuration = _entry(
        "aaa-config", "AI 全局配置", tags=["AI"], keywords=["ai"],
        related=[_link(video.document_id) for video in videos],
    )
    index = _index(configuration, *videos)
    result = retrieve_from_index(index, "AI视频", limit=4)
    assert len(result.candidates) == 4
    assert all(c.document_id.startswith("video-") for c in result.candidates)
    all_results = retrieve_from_index(index, "AI 视频")
    config = next(c for c in all_results.candidates if c.document_id == "aaa-config")
    assert config.score < min(c.score for c in result.candidates)
    assert config.score < 1
    assert len(config.evidence.related) == 5
    assert abs(sum(r.score for r in config.reasons if r.field == "related") - 0.1) < 0.001
