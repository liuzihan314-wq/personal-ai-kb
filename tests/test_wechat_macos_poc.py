import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.wechat_macos_poc.classifier import Decision, classify_metadata, is_new_candidate
from scripts.wechat_macos_poc.observation import observe_database
from scripts.wechat_macos_poc.probe import run_synthetic_probe


def article_metadata(**overrides: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "item_id": "synthetic-article-001",
        "source_type": "wechat",
        "publisher_type": "official_account",
        "content_type": "article",
        "url": "https://mp.weixin.qq.com/s/synthetic-article-001",
    }
    metadata.update(overrides)
    return metadata


def test_accepts_only_explicit_official_account_article_metadata():
    result = classify_metadata(article_metadata())

    assert result.decision is Decision.ACCEPT_CANDIDATE
    assert result.accepted
    assert result.reason == "explicit_official_account_article"


def test_forbidden_media_and_ordinary_url_never_become_candidates():
    samples = (
        article_metadata(content_type="video"),
        article_metadata(
            publisher_type="video_account",
            content_type="video",
            url="https://channels.weixin.qq.com/synthetic-video-account-001",
        ),
        article_metadata(
            publisher_type="unknown",
            content_type="url",
            url="https://example.invalid/synthetic-url-001",
        ),
    )

    results = [classify_metadata(sample) for sample in samples]

    assert all(result.decision is Decision.REJECT for result in results)
    assert all(not result.accepted for result in results)


def test_ambiguous_article_is_held_for_review():
    result = classify_metadata(article_metadata(publisher_type="unknown"))

    assert result.decision is Decision.REVIEW
    assert result.reason == "missing_official_account_marker"
    assert not result.accepted


def test_article_url_without_stable_id_is_not_incremental_candidate():
    result = classify_metadata(article_metadata(item_id=""))

    assert result.decision is Decision.REVIEW
    assert result.reason == "missing_stable_item_id"
    assert not result.accepted


def test_new_candidate_check_is_deterministic_and_does_not_mutate_seen_ids():
    metadata = article_metadata()
    seen_ids = {"synthetic-article-000"}

    assert is_new_candidate(metadata, seen_ids)
    assert seen_ids == {"synthetic-article-000"}
    assert not is_new_candidate(metadata, {"synthetic-article-001"})


def test_synthetic_probe_accepts_only_the_article_case():
    result = run_synthetic_probe()

    assert result["case_count"] == 5
    assert result["accepted_count"] == 1
    assert result["accepted_case_names"] == ["official_account_article"]
    assert {case["case"] for case in result["cases"]} == {
        "official_account_article",
        "video",
        "video_account",
        "ordinary_url",
        "ambiguous_article",
    }


def test_observer_reports_opaque_file_without_reading_rows(tmp_path):
    path = tmp_path / "synthetic-opaque.db"
    path.write_bytes(b"not a sqlite database")

    result = observe_database(path)

    assert result.exists
    assert result.size_bytes == len(b"not a sqlite database")
    assert not result.has_sqlite_header
    assert not result.sqlite_readable
    assert result.error_kind == "missing_sqlite_header"


def test_observer_opens_sqlite_only_in_read_only_mode(tmp_path):
    path = tmp_path / "synthetic.db"
    import sqlite3

    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE marker (value TEXT)")
        connection.commit()
    finally:
        connection.close()

    before = path.stat().st_size
    result = observe_database(path)

    assert result.exists
    assert result.has_sqlite_header
    assert result.sqlite_readable
    assert result.error_kind is None
    assert path.stat().st_size == before
