import base64
import json
from pathlib import Path

import pymupdf
import pytest
from typer.testing import CliRunner

from pkb.cli.main import app
from pkb.ingest.pdf import PDFImporter, UnsupportedPDFError
from pkb.storage import RawStorage


runner = CliRunner()


def _write_text_pdf(path: Path, *, text: str, title: str = "Synthetic PDF") -> None:
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), text)
    pdf.set_metadata({"title": title, "author": "Public Test Fixture"})
    pdf.save(path)
    pdf.close()


def _write_image_only_pdf(path: Path) -> None:
    image_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_image(pymupdf.Rect(0, 0, 100, 100), stream=image_bytes)
    pdf.save(path)
    pdf.close()


def test_text_pdf_creates_document_and_readable_immutable_raw_files(tmp_path):
    source = tmp_path / "sample.pdf"
    raw_dir = tmp_path / "data" / "raw"
    _write_text_pdf(source, text="A synthetic text layer for import.")

    document = PDFImporter(raw_dir=raw_dir).import_file(source)
    paths = RawStorage(raw_dir).paths_for(document.id)
    metadata = json.loads(paths.metadata_file.read_text(encoding="utf-8"))

    assert document.content_type == "pdf"
    assert document.source_type == "pdf"
    assert document.title == "Synthetic PDF"
    assert "synthetic text layer" in document.content
    assert paths.original_file.read_bytes() == source.read_bytes()
    assert paths.extracted_text_file.read_text(encoding="utf-8") == document.content
    assert metadata["id"] == document.id
    assert metadata["title"] == "Synthetic PDF"
    assert metadata["metadata"]["page_count"] == 1
    assert metadata["metadata"]["sha256"] == document.id
    assert "content" not in metadata


def test_reimport_same_pdf_returns_existing_document_without_new_raw_record(tmp_path):
    source = tmp_path / "sample.pdf"
    raw_dir = tmp_path / "data" / "raw"
    _write_text_pdf(source, text="The same source bytes must deduplicate.")
    importer = PDFImporter(raw_dir=raw_dir)

    first = importer.import_file(source)
    original_before = Path(first.original_file).read_bytes()
    second = importer.import_file(source)

    assert second == first
    assert Path(first.original_file).read_bytes() == original_before
    assert sorted(raw_dir.glob("*/original.pdf")) == [Path(first.original_file)]
    assert sorted(raw_dir.glob("*/extracted.txt")) == [
        raw_dir / first.id / "extracted.txt"
    ]


def test_image_only_pdf_is_rejected_without_creating_raw_record(tmp_path):
    source = tmp_path / "scan.pdf"
    raw_dir = tmp_path / "data" / "raw"
    _write_image_only_pdf(source)

    with pytest.raises(UnsupportedPDFError, match="无可提取文本.*OCR"):
        PDFImporter(raw_dir=raw_dir).import_file(source)

    assert not raw_dir.exists()


def test_cli_import_pdf_uses_configured_raw_directory(tmp_path, monkeypatch):
    source = tmp_path / "sample.pdf"
    data_dir = tmp_path / "data"
    _write_text_pdf(source, text="CLI import fixture.")
    monkeypatch.setenv("PKB_DATA_DIR", str(data_dir))

    result = runner.invoke(app, ["import-pdf", str(source)])

    assert result.exit_code == 0, result.output
    assert "status: imported" in result.output
    assert "raw_pdf:" in result.output
    assert len(list((data_dir / "raw").glob("*/original.pdf"))) == 1
