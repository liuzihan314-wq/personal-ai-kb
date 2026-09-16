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
from pkb.ingest import (
    IdeaCardImporter,
    PDFImporter,
    WeChatArticleService,
    WeChatImportResult,
)
from pkb.knowledge import KnowledgeCompiler, KnowledgeRecord
from pkb.models import UnifiedDocument
from pkb.notes import NoteGenerationResult, NoteService
from pkb.providers import AIProvider, configured_provider, provider_from_values
from pkb.qa import QAResult, QAService
from pkb.retrieval import (
    DashScopeEmbeddingClient,
    EmbeddingClient,
    RetrievalResult,
    RetrievalService,
)
from pkb.scripts import ScriptResult, ScriptWriter
from pkb.topics import TopicCandidate, TopicGenerationResult, TopicGenerator


_EMBEDDING_UNSET = object()


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
        embedding_client: EmbeddingClient | None | object = _EMBEDDING_UNSET,
    ) -> None:
        self.paths = paths or UIPaths.from_settings()
        # Core services keep MockAIProvider for deterministic unit tests.  The
        # user-facing UI must never present that fixture text as an AI answer.
        self.provider = provider if provider is not None else configured_provider()
        # An injected Provider/Embedding client is an explicit composition
        # choice.  Do not silently supplement it with this machine's .env.
        # The normal app path leaves both unset and therefore loads local
        # embedding configuration automatically.
        if embedding_client is _EMBEDDING_UNSET:
            self.embedding_client = (
                self._configured_embedding_client() if provider is None else None
            )
        else:
            self.embedding_client = embedding_client

    @staticmethod
    def _configured_embedding_client() -> EmbeddingClient | None:
        """Load the local embedding configuration without using process env vars."""

        settings = get_settings()
        api_key = (
            settings.embedding_api_key.get_secret_value()
            if settings.embedding_api_key
            else ""
        )
        values = (settings.embedding_model or "", settings.embedding_base_url or "", api_key)
        if not all(value.strip() for value in values):
            return None
        return DashScopeEmbeddingClient(
            model=values[0], base_url=values[1], api_key=values[2]
        )

    @classmethod
    def with_session_provider(
        cls,
        paths: UIPaths,
        *,
        provider_name: str,
        model: str,
        base_url: str,
        api_key: str,
        embedding_model: str | None = None,
        embedding_base_url: str | None = None,
        embedding_api_key: str | None = None,
    ) -> "UIService":
        """Bind a browser-session Provider without persisting its API key."""

        embedding_client = None
        embedding_values = (
            (embedding_model or "").strip(),
            (embedding_base_url or "").strip(),
            (embedding_api_key or "").strip(),
        )
        if all(embedding_values):
            embedding_client = DashScopeEmbeddingClient(
                model=embedding_values[0],
                base_url=embedding_values[1],
                api_key=embedding_values[2],
            )
        return cls(
            paths,
            provider=provider_from_values(provider_name, model, base_url, api_key),
            embedding_client=embedding_client,
        )

    @classmethod
    def with_session_embedding(
        cls,
        paths: UIPaths,
        *,
        embedding_model: str,
        embedding_base_url: str,
        embedding_api_key: str,
        provider: AIProvider | None = None,
    ) -> "UIService":
        """Bind only a browser-session Embedding client."""

        return cls(
            paths,
            provider=provider,
            embedding_client=DashScopeEmbeddingClient(
                model=embedding_model,
                base_url=embedding_base_url,
                api_key=embedding_api_key,
            ),
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

    def import_wechat_article(
        self,
        source_url: str,
        *,
        title: str | None = None,
        content: str | None = None,
    ) -> WeChatImportResult:
        """Import one WeChat article through the shared Core Service."""

        return WeChatArticleService(
            raw_dir=self.paths.raw_dir,
            notes_dir=self.paths.notes_dir,
            index_path=self.paths.index_path,
            provider=self.provider,
        ).import_article(source_url, title=title, content=content)

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        include_embeddings: bool = True,
    ) -> RetrievalResult:
        """Search the current local Index."""

        return RetrievalService(self.paths.index_path).search(
            query,
            limit=limit,
            embedding_client=self.embedding_client if include_embeddings else None,
        )

    def answer(
        self,
        question: str,
        *,
        limit: int = 10,
        include_embeddings: bool = True,
    ) -> QAResult:
        """Answer from the local Knowledge, Notes, and Raw stores."""

        return QAService(
            index_path=self.paths.index_path,
            knowledge_dir=self.paths.knowledge_dir,
            notes_dir=self.paths.notes_dir,
            raw_dir=self.paths.raw_dir,
            provider=self.provider,
            embedding_client=self.embedding_client if include_embeddings else None,
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
