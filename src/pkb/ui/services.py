"""Thin Streamlit-facing composition of the existing Core Services.

The UI layer owns only input adaptation, path binding, and orchestration.  It
does not implement parsing, indexing, retrieval, synthesis, topic scoring, or
script generation itself.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from pkb.config import Settings, get_settings
from pkb.index import IndexBuilder, IndexFile
from pkb.ingest import IdeaCardImporter, PDFImporter
from pkb.knowledge import KnowledgeCompiler, KnowledgeRecord
from pkb.models import UnifiedDocument
from pkb.notes import NoteGenerationResult, NoteService
from pkb.providers import AIProvider, configured_provider, provider_from_values
from pkb.qa import QAResult, QAService
from pkb.retrieval import RetrievalResult, RetrievalService
from pkb.scripts import ScriptResult, ScriptWriter
from pkb.topics import TopicCandidate, TopicGenerationResult, TopicGenerator


@dataclass(frozen=True)
class UIPaths:
    """The local directories used by the Streamlit entry point."""

    data_dir: Path

    @classmethod
    def from_data_dir(cls, data_dir: str | Path) -> "UIPaths":
        return cls(data_dir=Path(data_dir))

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "UIPaths":
        configured = settings or get_settings()
        return cls.from_data_dir(configured.data_dir)

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def notes_dir(self) -> Path:
        return self.data_dir / "notes"

    @property
    def knowledge_dir(self) -> Path:
        return self.data_dir / "knowledge"

    @property
    def index_path(self) -> Path:
        return self.data_dir / "index" / "index.json"


@dataclass(frozen=True)
class IngestResult:
    """The persisted artifacts produced by one UI import action."""

    document: UnifiedDocument
    note: NoteGenerationResult
    index: IndexFile


def find_candidate(
    candidates: Sequence[TopicCandidate],
    title: str | None,
) -> TopicCandidate | None:
    """Resolve a displayed candidate title without inventing a selection."""

    if not title:
        return None
    return next((candidate for candidate in candidates if candidate.title == title), None)


def can_generate_script(
    candidates: Sequence[TopicCandidate],
    selected_title: str | None,
    confirmed: bool,
) -> bool:
    """Return whether the UI has an explicit, still-valid topic selection."""

    return bool(confirmed and find_candidate(candidates, selected_title) is not None)


class UIService:
    """Bind UI actions to the existing application services."""

    def __init__(
        self,
        paths: UIPaths | None = None,
        *,
        provider: AIProvider | None = None,
    ) -> None:
        self.paths = paths or UIPaths.from_settings()
        # Core services keep MockAIProvider for deterministic unit tests.  The
        # user-facing UI must never present that fixture text as an AI answer.
        self.provider = provider if provider is not None else configured_provider()

    @classmethod
    def with_session_provider(
        cls,
        paths: UIPaths,
        *,
        provider_name: str,
        model: str,
        base_url: str,
        api_key: str,
    ) -> "UIService":
        """Bind a browser-session Provider without persisting its API key."""

        return cls(
            paths,
            provider=provider_from_values(provider_name, model, base_url, api_key),
        )

    def _persist_ingest(self, document: UnifiedDocument) -> IngestResult:
        note = NoteService(
            provider=self.provider,
            notes_dir=self.paths.notes_dir,
        ).generate(document)
        index = IndexBuilder(
            notes_dir=self.paths.notes_dir,
            index_path=self.paths.index_path,
        ).rebuild()
        return IngestResult(document=document, note=note, index=index)

    def import_pdf(self, filename: str, content: bytes) -> IngestResult:
        """Import one uploaded PDF through ``PDFImporter``.

        ``PDFImporter`` intentionally accepts a filesystem path, so the
        uploaded bytes are exposed through a cross-platform temporary path and
        then handed to the existing importer unchanged.
        """

        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("PDF 文件名不能为空")
        if not isinstance(content, bytes):
            raise TypeError("PDF 内容必须是 bytes")

        source_name = Path(filename).name
        if source_name in {"", ".", ".."}:
            source_name = "upload.pdf"
        with TemporaryDirectory(prefix="pkb-ui-") as directory:
            source_path = Path(directory) / source_name
            source_path.write_bytes(content)
            document = PDFImporter(raw_dir=self.paths.raw_dir).import_file(source_path)
        return self._persist_ingest(document)

    def add_idea(
        self,
        content: str,
        *,
        source_url: str | None = None,
        tags: Sequence[str] | None = None,
        note: str | None = None,
    ) -> IngestResult:
        """Save one idea card and update the local Note/Index views."""

        document = IdeaCardImporter(raw_dir=self.paths.raw_dir).create(
            content,
            source_url=source_url,
            tags=tags,
            note=note,
        )
        return self._persist_ingest(document)

    def search(self, query: str, *, limit: int = 10) -> RetrievalResult:
        """Search the current local Index."""

        return RetrievalService(self.paths.index_path).search(query, limit=limit)

    def answer(self, question: str, *, limit: int = 10) -> QAResult:
        """Answer from the local Knowledge, Notes, and Raw stores."""

        return QAService(
            index_path=self.paths.index_path,
            knowledge_dir=self.paths.knowledge_dir,
            notes_dir=self.paths.notes_dir,
            raw_dir=self.paths.raw_dir,
            provider=self.provider,
        ).answer(question, limit=limit)

    def synthesize_topic(self, topic: str) -> KnowledgeRecord:
        """Compile all existing Notes for one topic through the Core."""

        return KnowledgeCompiler(
            provider=self.provider,
            knowledge_dir=self.paths.knowledge_dir,
            notes_dir=self.paths.notes_dir,
        ).compile(topic)

    def generate_topics(self, *, limit: int = 5) -> TopicGenerationResult:
        """Generate explainable topic candidates from local persisted data."""

        return TopicGenerator(
            index_path=self.paths.index_path,
            knowledge_dir=self.paths.knowledge_dir,
            notes_dir=self.paths.notes_dir,
        ).generate(limit=limit)

    def write_script(
        self,
        selected_topic: TopicCandidate | str | None = None,
        *,
        confirmed: bool = False,
        limit: int = 10,
    ) -> ScriptResult:
        """Write only after confirmation; ScriptWriter performs fresh retrieval."""

        return ScriptWriter(
            index_path=self.paths.index_path,
            knowledge_dir=self.paths.knowledge_dir,
            notes_dir=self.paths.notes_dir,
            raw_dir=self.paths.raw_dir,
            provider=self.provider,
        ).write(selected_topic, confirmed=confirmed, limit=limit)


__all__ = [
    "IngestResult",
    "UIPaths",
    "UIService",
    "can_generate_script",
    "find_candidate",
]
