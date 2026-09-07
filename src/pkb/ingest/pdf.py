"""Adapter for importing PDFs that already contain a readable text layer."""

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Callable

import pymupdf

from pkb.config import get_settings
from pkb.models import UnifiedDocument
from pkb.storage import RawStorage


class PDFImportError(ValueError):
    """Raised when a PDF cannot be imported under the V1 contract."""


class UnsupportedPDFError(PDFImportError):
    """Raised for PDFs without any extractable text layer."""


class PDFImporter:
    """Import text PDFs into UnifiedDocument and immutable Raw storage."""

    def __init__(
        self,
        raw_storage: RawStorage | None = None,
        *,
        raw_dir: str | Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if raw_storage is not None and raw_dir is not None:
            raise ValueError("Pass raw_storage or raw_dir, not both")
        self.raw_storage = raw_storage or RawStorage(
            raw_dir if raw_dir is not None else get_settings().raw_dir
        )
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def import_file(self, file_path: str | Path) -> UnifiedDocument:
        """Import one text PDF, deduplicating by its exact source bytes."""

        source_path = Path(file_path)
        if source_path.suffix.lower() != ".pdf":
            raise PDFImportError("仅支持 PDF 文件（扩展名必须为 .pdf）")

        pdf_bytes = source_path.read_bytes()
        document_id = sha256(pdf_bytes).hexdigest()
        if self.raw_storage.has_document(document_id):
            return self.raw_storage.load_document(document_id)

        try:
            pdf = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except pymupdf.FileDataError as exc:
            raise PDFImportError(f"无法读取 PDF：{source_path}") from exc

        with pdf:
            pdf_metadata = dict(pdf.metadata or {})
            page_texts = [
                page.get_text("text", sort=True).strip() for page in pdf
            ]
            content = "\n\n".join(text for text in page_texts if text).strip()
            if not content:
                raise UnsupportedPDFError(
                    "PDF 不支持：无可提取文本；扫描/图片型 PDF 不处理，也不会调用 OCR。"
                )

            title = str(pdf_metadata.get("title") or source_path.stem).strip()
            author_value = pdf_metadata.get("author")
            author = str(author_value).strip() if author_value else None
            page_count = pdf.page_count

        raw_paths = self.raw_storage.paths_for(document_id)
        document = UnifiedDocument(
            id=document_id,
            content_type="pdf",
            title=title,
            content=content,
            source_type="pdf",
            author=author,
            ingested_at=self.clock(),
            original_file=str(raw_paths.original_file),
            metadata={
                "sha256": document_id,
                "file_size": len(pdf_bytes),
                "page_count": page_count,
                "pdf_metadata": pdf_metadata,
                "extracted_text_file": str(raw_paths.extracted_text_file),
                "metadata_file": str(raw_paths.metadata_file),
            },
        )
        return self.raw_storage.store(document, pdf_bytes)


def import_pdf(
    file_path: str | Path,
    *,
    raw_dir: str | Path | None = None,
) -> UnifiedDocument:
    """Convenience function for importing one PDF with configured storage."""

    return PDFImporter(raw_dir=raw_dir).import_file(file_path)
