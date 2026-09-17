"""Tests for user-scoped history and audit records (TASK-030)."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest

from pkb.history import HistoryRecord, HistoryStorageError, HistoryStore
from pkb.providers import MockAIProvider
from pkb.ui import UIPaths, UIService


def _user_id(subject: str) -> str:
    """Reproduce the auth adapter's stable internal user id."""

    digest = sha256(f"https://test.example.com\0{subject}".encode("utf-8")).hexdigest()
    return f"u_{digest}"


def _record(
    kind,
    *,
    created_at: datetime,
    status: str = "ok",
    message: str = "记录已保存",
) -> HistoryRecord:
    return HistoryRecord(
        id=uuid4().hex,
        kind=kind,
        created_at=created_at,
        status=status,
        question="问题" if kind == "qa" else None,
        message=message,
    )


def test_history_store_appends_without_overwrite(tmp_path: Path) -> None:
    """Append is durable and refuses to replace an existing record."""

    store = HistoryStore(tmp_path)
    record = _record("qa", created_at=datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc))

    path = store.append(record)
    assert path == tmp_path / f"{record.id}.json"
    assert path.exists()

    with pytest.raises(HistoryStorageError, match="拒绝覆盖"):
        store.append(record)
    assert store.list_records() == [record]


def test_history_store_returns_chronological_order(tmp_path: Path) -> None:
    """Records are read back in creation-time order, not filesystem order."""

    store = HistoryStore(tmp_path)
    later = _record("topic", created_at=datetime(2026, 9, 17, 10, 0, tzinfo=timezone.utc))
    earlier = _record("qa", created_at=datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc))

    store.append(later)
    store.append(earlier)

    assert store.list_records() == [earlier, later]


def test_history_store_rejects_corrupt_record(tmp_path: Path) -> None:
    """Corrupt history files are surfaced, not silently treated as empty."""

    store = HistoryStore(tmp_path)
    (tmp_path / "broken.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(HistoryStorageError, match="历史记录损坏"):
        store.list_records()


def test_history_is_scoped_to_each_user(tmp_path: Path) -> None:
    """Alice's Q&A/topic history must never appear in Bob's listing."""

    alice = UIService(
        paths=UIPaths.from_data_dir(tmp_path, user_id=_user_id("alice")),
        provider=MockAIProvider(),
    )
    bob = UIService(
        paths=UIPaths.from_data_dir(tmp_path, user_id=_user_id("bob")),
        provider=MockAIProvider(),
    )

    alice.add_idea("Alice 的私有灵感", tags=["private"])
    bob.add_idea("Bob 的私有灵感", tags=["private"])
    alice.answer("Alice 的私有灵感是什么？")
    bob.answer("Bob 的私有灵感是什么？")
    alice.generate_topics()

    alice_records = alice.list_history()
    bob_records = bob.list_history()

    assert {record.kind for record in alice_records} == {"qa", "topic"}
    assert bob_records
    assert all(record.kind == "qa" for record in bob_records)
    assert all("Alice" in (record.question or "") for record in alice_records if record.kind == "qa")
    assert all("Alice" not in (record.question or "") for record in bob_records)


def test_script_result_is_recorded_after_generation(tmp_path: Path) -> None:
    """A generated spoken script is appended to the current user's history."""

    service = UIService(
        paths=UIPaths.from_data_dir(tmp_path, user_id=_user_id("alice")),
        provider=MockAIProvider(),
    )
    service.add_idea("先改流程，再换工具。", tags=["AI", "workflow"])
    service.add_idea("把 AI 工具组合成可复用的效率流程。", tags=["AI", "workflow"])
    service.add_idea("自动化要嵌入工作流，先验证具体任务的收益。", tags=["automation", "workflow"])

    topics = service.generate_topics()
    assert topics.candidates
    script = service.write_script(topics.candidates[0], confirmed=True)
    assert script.status == "generated"

    records = service.list_history()
    assert records[-1].kind == "script"
    assert records[-1].status == "generated"
    assert records[-1].topic == script.topic
    assert records[-1].script_title == script.title
