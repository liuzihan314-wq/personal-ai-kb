from datetime import datetime, timezone
from pathlib import Path

import pymupdf
from typer.testing import CliRunner

from pkb.cli.main import app
from pkb.ingest.idea import IdeaCardImporter
from pkb.ingest.pdf import PDFImporter
from pkb.models import UnifiedDocument
from pkb.notes import NoteService, parse_note
from pkb.providers import MockAIProvider


runner = CliRunner()
FIXED_TIME = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def _write_text_pdf(path: Path, text: str) -> None:
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), text)
    pdf.set_metadata({"title": "Synthetic Notes PDF"})
    pdf.save(path)
    pdf.close()


def test_pdf_note_is_traceable_and_does_not_change_raw(tmp_path):
    source = tmp_path / "source.pdf"
    raw_dir = tmp_path / "data" / "raw"
    notes_dir = tmp_path / "data" / "notes"
    _write_text_pdf(source, "A synthetic PDF explains traceable AI notes.")
    document = PDFImporter(raw_dir=raw_dir).import_file(source)
    raw_before = {
        path: path.read_bytes()
        for path in Path(document.original_file).parent.iterdir()
        if path.is_file()
    }

    provider = MockAIProvider(
        responses={
            "summarize": "A concise PDF summary.",
            "extract_key_points": ["The note keeps a source trail."],
            "extract_quotes": ["Traceability matters."],
            "generate_tags": ["notes", "traceability"],
        }
    )
    result = NoteService(
        provider=provider,
        notes_dir=notes_dir,
        clock=lambda: FIXED_TIME,
    ).generate(document)

    markdown = result.path.read_text(encoding="utf-8")
    assert result.created is True
    assert result.path == notes_dir / f"{document.id}.md"
    assert markdown.startswith("---\ndocument_id:")
    assert 'source_type: "pdf"' in markdown
    assert 'title: "Synthetic Notes PDF"' in markdown
    assert 'tags:\n  - "notes"\n  - "traceability"' in markdown
    assert "## Summary" in markdown
    assert "## Key points" in markdown
    assert "## Quotes" in markdown
    assert "## Source" in markdown
    assert document.id in markdown
    assert document.original_file in markdown
    assert parse_note(markdown) == result.note
    assert raw_before == {
        path: path.read_bytes()
        for path in Path(document.original_file).parent.iterdir()
        if path.is_file()
    }
    assert provider.calls == [
        "summarize",
        "extract_key_points",
        "extract_quotes",
        "generate_tags",
    ]


def test_idea_note_keeps_original_viewpoint_in_a_lightweight_shape(tmp_path):
    raw_dir = tmp_path / "data" / "raw"
    notes_dir = tmp_path / "data" / "notes"
    document = IdeaCardImporter(raw_dir=raw_dir).create(
        "先做一个真实样本，再扩展自动化。",
        source_url="https://example.test/idea",
        tags=["workflow"],
        note="下次补一个失败案例。",
    )
    provider = MockAIProvider(
        responses={
            "summarize": "先验证最小闭环。",
            "extract_key_points": ["真实样本优先。"],
            "extract_quotes": ["先做一个真实样本。"],
            "generate_tags": ["workflow", "validation"],
        }
    )

    result = NoteService(
        provider=provider,
        notes_dir=notes_dir,
        clock=lambda: FIXED_TIME,
    ).generate(document)
    markdown = result.path.read_text(encoding="utf-8")

    assert "## Original idea" in markdown
    assert "先做一个真实样本，再扩展自动化。" in markdown
    assert "## Personal note" in markdown
    assert "下次补一个失败案例。" in markdown
    assert "## Summary" in markdown
    assert result.note.tags == ["workflow", "validation"]
    assert result.note.source_url == "https://example.test/idea"
    assert result.note.original_file == document.original_file
    assert "long-form article" not in markdown.lower()


def test_duplicate_generation_returns_existing_note_without_overwriting(tmp_path):
    document = UnifiedDocument(
        id="document-duplicate",
        content_type="idea",
        title="Duplicate test",
        content="The first generated note is immutable.",
        source_type="manual",
    )
    notes_dir = tmp_path / "notes"
    first_provider = MockAIProvider(
        responses={
            "summarize": "First summary.",
            "extract_key_points": ["First point."],
            "extract_quotes": ["First quote."],
            "generate_tags": ["first"],
        }
    )
    first = NoteService(
        provider=first_provider,
        notes_dir=notes_dir,
        clock=lambda: FIXED_TIME,
    ).generate(document)
    before = first.path.read_bytes()

    second_provider = MockAIProvider(
        responses={
            "summarize": "A different summary that must not replace the first.",
            "generate_tags": ["second"],
        }
    )
    second = NoteService(provider=second_provider, notes_dir=notes_dir).generate(document)

    assert second.created is False
    assert second.note == first.note
    assert second.path == first.path
    assert second.path.read_bytes() == before
    assert second_provider.calls == []


def test_five_synthetic_pdf_and_idea_documents_generate_notes(tmp_path):
    notes_dir = tmp_path / "notes"
    documents = [
        UnifiedDocument(
            id=f"synthetic-{index}",
            content_type="pdf" if index < 3 else "idea",
            title=f"Synthetic {index}",
            content=f"Synthetic source {index} for note generation.",
            source_type="pdf" if index < 3 else "manual",
            original_file=f"data/raw/synthetic-{index}/original.txt",
        )
        for index in range(5)
    ]

    for document in documents:
        result = NoteService(notes_dir=notes_dir, clock=lambda: FIXED_TIME).generate(document)
        assert result.path.is_file()
        assert result.note.document_id == document.id
        assert result.note.summary

    assert len(list(notes_dir.glob("*.md"))) == 5


def test_cli_generate_note_reads_raw_and_is_idempotent(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("PKB_DATA_DIR", str(data_dir))
    document = IdeaCardImporter(raw_dir=data_dir / "raw").create(
        "CLI 合成观点：来源必须可追溯。",
        tags=["cli"],
    )

    first = runner.invoke(app, ["generate-note", document.id])
    second = runner.invoke(app, ["generate-note", document.id])

    assert first.exit_code == 0, first.output
    assert "status: generated" in first.output
    assert "source_type: manual" in first.output
    assert second.exit_code == 0, second.output
    assert "status: existing" in second.output
    assert len(list((data_dir / "notes").glob("*.md"))) == 1
