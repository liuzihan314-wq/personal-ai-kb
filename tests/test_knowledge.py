from datetime import datetime, timezone
from pathlib import Path

import pytest

from pkb.knowledge import (
    KnowledgeCompilationError,
    KnowledgeCompiler,
    KnowledgeStorage,
    KnowledgeTopicConflictError,
    parse_knowledge,
)
from pkb.notes import Note, NoteStorage
from pkb.providers import MockAIProvider


FIXED_TIME = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
UPDATED_TIME = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def _note(document_id: str, index: int) -> Note:
    return Note(
        document_id=document_id,
        source_type="pdf" if index < 3 else "manual",
        title=f"AI workflow source {index}",
        created_at=FIXED_TIME,
        tags=["ai-workflow"],
        summary=f"Source {index} explains a traceable AI workflow.",
        key_points=[f"Workflow point {index} stays grounded in the Note."],
        quotes=[f"Keep source {index} traceable."],
        source_reference=f"raw:{document_id}",
        original_file=f"data/raw/{document_id}/original.txt",
    )


def _write_notes(notes_dir: Path, notes: list[Note]) -> None:
    storage = NoteStorage(notes_dir)
    for note in notes:
        storage.write(note)


def test_five_notes_compile_to_readable_traceable_topic_knowledge(tmp_path):
    notes_dir = tmp_path / "data" / "notes"
    knowledge_dir = tmp_path / "data" / "knowledge"
    raw_dir = tmp_path / "data" / "raw"
    notes = [_note(f"synthetic-{index}", index) for index in range(5)]
    _write_notes(notes_dir, notes)
    for note in notes:
        source_dir = raw_dir / note.document_id
        source_dir.mkdir(parents=True)
        (source_dir / "original.txt").write_text(
            f"Raw source {note.document_id}",
            encoding="utf-8",
        )

    note_before = {
        path: path.read_bytes() for path in notes_dir.glob("*.md")
    }
    raw_before = {
        path: path.read_bytes()
        for path in raw_dir.rglob("*")
        if path.is_file()
    }
    provider = MockAIProvider(
        responses={"compile_topic": "Current synthesis from five local Notes."}
    )

    result = KnowledgeCompiler(
        provider=provider,
        notes_dir=notes_dir,
        knowledge_dir=knowledge_dir,
        clock=lambda: FIXED_TIME,
    ).compile("AI workflow")

    assert result.created is True
    assert result.path.is_file()
    assert result.path.parent == knowledge_dir
    markdown = result.path.read_text(encoding="utf-8")
    assert markdown.startswith("---\ntopic:")
    assert "created_at:" in markdown
    assert "updated_at:" in markdown
    assert "source_note_ids:" in markdown
    assert "source_references:" in markdown
    assert "## Current synthesis" in markdown
    assert "## Sources" in markdown
    assert result.knowledge.source_note_ids == [note.document_id for note in notes]
    assert result.knowledge.source_references == [note.source_reference for note in notes]
    assert parse_knowledge(markdown) == result.knowledge
    assert provider.calls == ["compile_topic"]
    assert note_before == {
        path: path.read_bytes() for path in notes_dir.glob("*.md")
    }
    assert raw_before == {
        path: path.read_bytes()
        for path in raw_dir.rglob("*")
        if path.is_file()
    }


def test_new_note_updates_same_topic_and_preserves_inputs(tmp_path):
    notes_dir = tmp_path / "notes"
    knowledge_dir = tmp_path / "knowledge"
    first_notes = [_note(f"source-{index}", index) for index in range(5)]
    _write_notes(notes_dir, first_notes)
    note_before = {
        path: path.read_bytes() for path in notes_dir.glob("*.md")
    }

    first = KnowledgeCompiler(
        provider=MockAIProvider(responses={"compile_topic": "First judgment."}),
        notes_dir=notes_dir,
        knowledge_dir=knowledge_dir,
        clock=lambda: FIXED_TIME,
    ).compile("AI workflow")
    first_bytes = first.path.read_bytes()

    new_note = _note("source-5", 5)
    NoteStorage(notes_dir).write(new_note)
    second_provider = MockAIProvider(
        responses={"compile_topic": "Updated judgment includes the new Note."}
    )
    second = KnowledgeCompiler(
        provider=second_provider,
        notes_dir=notes_dir,
        knowledge_dir=knowledge_dir,
        clock=lambda: UPDATED_TIME,
    ).compile("AI workflow")

    assert second.created is False
    assert second.updated is True
    assert second.path == first.path
    assert second.path.read_bytes() != first_bytes
    assert second.knowledge.created_at == FIXED_TIME
    assert second.knowledge.updated_at == UPDATED_TIME
    assert second.knowledge.source_note_ids == [
        note.document_id for note in [*first_notes, new_note]
    ]
    assert second.knowledge.current_synthesis == (
        "Updated judgment includes the new Note."
    )
    assert note_before == {
        path: path.read_bytes() for path in notes_dir.glob("*.md") if path.name != "source-5.md"
    }
    assert second_provider.calls == ["compile_topic"]


def test_index_entries_can_be_used_as_read_only_compile_input(tmp_path):
    notes_dir = tmp_path / "notes"
    knowledge_dir = tmp_path / "knowledge"
    notes = [_note("indexed-source", 0)]
    _write_notes(notes_dir, notes)

    from pkb.index import IndexBuilder

    index = IndexBuilder(notes_dir, clock=lambda: FIXED_TIME).build()
    result = KnowledgeCompiler(
        provider=MockAIProvider(
            responses={"compile_topic": "Compiled from an Index-selected Note."}
        ),
        knowledge_dir=knowledge_dir,
        clock=lambda: FIXED_TIME,
    ).compile("Indexed topic", index)

    assert result.knowledge.source_note_ids == ["indexed-source"]
    assert "Indexed topic" in result.path.read_text(encoding="utf-8")


def test_empty_or_invalid_notes_fail_before_writing_knowledge(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    compiler = KnowledgeCompiler(
        provider=MockAIProvider(),
        knowledge_dir=knowledge_dir,
    )

    with pytest.raises(KnowledgeCompilationError, match="No Notes"):
        compiler.compile("Empty topic", [])
    assert not knowledge_dir.exists()

    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "broken.md").write_text("# not a Note\n", encoding="utf-8")
    with pytest.raises(KnowledgeCompilationError, match="Invalid Note file"):
        KnowledgeCompiler(notes_dir=notes_dir, knowledge_dir=knowledge_dir).compile(
            "Broken topic"
        )
    assert not knowledge_dir.exists()


def test_topic_paths_are_safe_stable_and_do_not_collide(tmp_path):
    storage = KnowledgeStorage(tmp_path / "knowledge")
    first = storage.path_for("AI / 视频: workflow")
    second = storage.path_for("AI / 视频: workflow")
    different = storage.path_for("AI 视频 workflow")

    assert first == second
    assert first != different
    assert first.suffix == ".md"
    assert all(character not in first.name for character in "/\\:*?\"<>|")


def test_storage_refuses_a_mismatched_topic_file(tmp_path):
    storage = KnowledgeStorage(tmp_path / "knowledge")
    path = storage.path_for("Topic one")
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\n"
        'topic: "Topic two"\n'
        'created_at: "2026-09-07T12:00:00+00:00"\n'
        'updated_at: "2026-09-07T12:00:00+00:00"\n'
        "source_note_ids:\n"
        '  - "source"\n'
        "source_references:\n"
        '  - "raw:source"\n'
        'source_titles:\n  - "Source"\n'
        'raw_document_ids:\n  - "source"\n'
        "---\n\n"
        "# Topic two\n\n"
        "## Current synthesis\n\nA synthesis.\n\n"
        "## Sources\n\n- source\n",
        encoding="utf-8",
    )

    with pytest.raises(KnowledgeTopicConflictError):
        storage.read("Topic one")
