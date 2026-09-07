import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pkb.cli.main import app
from pkb.index import IndexBuildError, IndexBuilder, IndexStorageError, read_index
from pkb.notes import Note, render_note


runner = CliRunner()
FIXED_TIME = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def _note(
    document_id: str,
    title: str,
    *,
    tags: list[str],
    summary: str,
    key_points: list[str] | None = None,
) -> Note:
    return Note(
        document_id=document_id,
        source_type="manual",
        title=title,
        created_at=FIXED_TIME,
        tags=tags,
        summary=summary,
        key_points=key_points or [],
    )


def _write_note(notes_dir: Path, note: Note) -> Path:
    notes_dir.mkdir(parents=True, exist_ok=True)
    path = notes_dir / f"{note.document_id}.md"
    path.write_text(render_note(note), encoding="utf-8")
    return path


def test_rebuild_writes_index_fields_and_explainable_bidirectional_related(tmp_path):
    notes_dir = tmp_path / "data" / "notes"
    index_path = tmp_path / "data" / "index" / "index.json"
    related_one = _note(
        "related-one",
        "Retrieval workflow",
        tags=["retrieval", "workflow"],
        summary="Deterministic rule scoring keeps local search explainable.",
        key_points=["Keep candidate ranking traceable."],
    )
    related_two = _note(
        "related-two",
        "Explainable retrieval",
        tags=["retrieval"],
        summary="Rule scoring keeps local search traceable.",
        key_points=["Use explicit reasons for each link."],
    )
    unrelated = _note(
        "unrelated",
        "Bread recipes",
        tags=["cooking"],
        summary="Bake bread with flour and water.",
        key_points=["Use a warm oven."],
    )
    first_path = _write_note(notes_dir, related_one)
    _write_note(notes_dir, related_two)
    _write_note(notes_dir, unrelated)

    index = IndexBuilder(
        notes_dir,
        index_path,
        clock=lambda: FIXED_TIME,
    ).rebuild()

    assert index_path.is_file()
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert {entry["document_id"] for entry in payload["entries"]} == {
        "related-one",
        "related-two",
        "unrelated",
    }
    first_entry = next(entry for entry in payload["entries"] if entry["document_id"] == "related-one")
    second_entry = next(entry for entry in payload["entries"] if entry["document_id"] == "related-two")
    unrelated_entry = next(entry for entry in payload["entries"] if entry["document_id"] == "unrelated")

    assert first_entry["title"] == "Retrieval workflow"
    assert first_entry["tags"] == ["retrieval", "workflow"]
    assert first_entry["keywords"]
    assert first_entry["source_type"] == "manual"
    assert first_entry["note_path"] == str(first_path)
    assert first_entry["topic"] is None
    assert [link["document_id"] for link in first_entry["related"]] == ["related-two"]
    assert [link["document_id"] for link in second_entry["related"]] == ["related-one"]
    assert "shared tags: retrieval" in first_entry["related"][0]["reason"]
    assert first_entry["related"][0]["reasons"][0]["rule"] == "shared_tags"
    assert unrelated_entry["related"] == []

    loaded = read_index(index_path)
    assert loaded == index


def test_rebuild_reflects_current_notes_without_mutating_notes(tmp_path):
    notes_dir = tmp_path / "notes"
    index_path = tmp_path / "index.json"
    first = _note(
        "first",
        "Local indexing",
        tags=["index"],
        summary="A local index keeps retrieval traceable.",
    )
    second = _note(
        "second",
        "Index rules",
        tags=["index"],
        summary="Explicit rules explain each local link.",
    )
    first_path = _write_note(notes_dir, first)
    second_path = _write_note(notes_dir, second)
    first_before = first_path.read_bytes()
    second_before = second_path.read_bytes()
    builder = IndexBuilder(notes_dir, index_path, clock=lambda: FIXED_TIME)

    assert len(builder.rebuild().entries) == 2

    third = _note(
        "third",
        "Bread baking",
        tags=["cooking"],
        summary="Bake bread with flour.",
    )
    _write_note(notes_dir, third)
    assert len(builder.rebuild().entries) == 3
    assert first_path.read_bytes() == first_before
    assert second_path.read_bytes() == second_before

    second_path.unlink()
    rebuilt = builder.rebuild()
    assert {entry.document_id for entry in rebuilt.entries} == {"first", "third"}
    assert first_path.read_bytes() == first_before


def test_invalid_note_does_not_replace_existing_index(tmp_path):
    notes_dir = tmp_path / "notes"
    index_path = tmp_path / "index.json"
    _write_note(
        notes_dir,
        _note(
            "valid",
            "Valid note",
            tags=["valid"],
            summary="This note has a valid summary.",
        ),
    )
    builder = IndexBuilder(notes_dir, index_path, clock=lambda: FIXED_TIME)
    builder.rebuild()
    index_before = index_path.read_bytes()

    (notes_dir / "broken.md").write_text("# no frontmatter\n", encoding="utf-8")
    with pytest.raises(IndexBuildError, match="Invalid Note file"):
        builder.rebuild()

    assert index_path.read_bytes() == index_before


def test_missing_and_corrupt_inputs_have_clear_errors(tmp_path):
    missing_notes = tmp_path / "missing-notes"
    with pytest.raises(IndexBuildError, match="Notes directory does not exist"):
        IndexBuilder(missing_notes).build()

    index_path = tmp_path / "broken-index.json"
    index_path.write_text("{not json", encoding="utf-8")
    with pytest.raises(IndexStorageError, match="Invalid JSON index"):
        read_index(index_path)


def test_cli_rebuild_and_status_use_configured_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("PKB_DATA_DIR", str(data_dir))
    _write_note(
        data_dir / "notes",
        _note(
            "cli-note",
            "CLI indexing",
            tags=["cli"],
            summary="The CLI rebuilds a local JSON index.",
        ),
    )

    rebuilt = runner.invoke(app, ["rebuild-index"])
    assert rebuilt.exit_code == 0, rebuilt.output
    assert "status: rebuilt" in rebuilt.output
    assert "notes: 1" in rebuilt.output
    assert (data_dir / "index" / "index.json").is_file()

    status = runner.invoke(app, ["index-status"])
    assert status.exit_code == 0, status.output
    assert "status: ok" in status.output
    assert "notes: 1" in status.output
