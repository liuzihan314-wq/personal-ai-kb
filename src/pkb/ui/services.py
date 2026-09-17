"""Thin Streamlit-facing composition of the existing Core Services.

The UI layer owns only input adaptation, path binding, and orchestration.  It
does not implement parsing, indexing, retrieval, synthesis, topic scoring, or
script generation itself.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from pkb.config import Settings, get_settings
from pkb.history import HistoryRecord, HistoryStore
from pkb.index import IndexBuilder, IndexFile
from pkb.ingest import (
    IdeaCardImporter,
    PDFImporter,
    WeChatArticleService,
    WeChatImportResult,
)
from pkb.knowledge import KnowledgeCompiler, KnowledgeRecord
from pkb.models import IdentityContext, UnifiedDocument
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
from pkb.storage import (
    UserScopeError,
    prepare_user_root,
    user_root_for_identity,
    validate_user_id,
)
from pkb.topics import TopicCandidate, TopicGenerationResult, TopicGenerator


_EMBEDDING_UNSET = object()


@dataclass(frozen=True)
class UIPaths:
    """The local directories used by the Streamlit entry point.

    When ``user_id`` is set, every content directory is scoped under
    ``<data_dir>/users/<user_id>/``.  When it is unset the legacy V1 layout
    under ``<data_dir>/`` is preserved so existing single-user deployments keep
    working without migration.
    """

    data_dir: Path
    user_id: str | None = None

    def __post_init__(self) -> None:
        if self.user_id is not None:
            # Reuse the storage-layer validator so the rules stay in one place.
            validate_user_id(self.user_id)

    @classmethod
    def from_data_dir(
        cls,
        data_dir: str | Path,
        *,
        user_id: str | None = None,
    ) -> "UIPaths":
        return cls(data_dir=Path(data_dir), user_id=user_id)

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        *,
        user_id: str | None = None,
    ) -> "UIPaths":
        configured = settings or get_settings()
        return cls.from_data_dir(configured.data_dir, user_id=user_id)

    def _content_root(self, name: str) -> Path:
        if self.user_id is not None:
            return self.data_dir / "users" / self.user_id / name
        return self.data_dir / name

    @property
    def raw_dir(self) -> Path:
        return self._content_root("raw")

    @property
    def notes_dir(self) -> Path:
        return self._content_root("notes")

    @property
    def knowledge_dir(self) -> Path:
        return self._content_root("knowledge")

    @property
    def index_path(self) -> Path:
        return self._content_root("index") / "index.json"

    @property
    def history_dir(self) -> Path:
        return self._content_root("history")


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
        identity: IdentityContext | None = None,
    ) -> None:
        if paths is not None and identity is not None:
            raise ValueError("paths 和 identity 不能同时提供")
        if identity is not None:
            user_root = prepare_user_root(user_root_for_identity(get_settings(), identity))
            self.paths = UIPaths.from_data_dir(user_root, user_id=identity.user_id)
        else:
            self.paths = paths or UIPaths.from_settings()
        self.history_store = HistoryStore(self.paths.history_dir)
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

        result = QAService(
            index_path=self.paths.index_path,
            knowledge_dir=self.paths.knowledge_dir,
            notes_dir=self.paths.notes_dir,
            raw_dir=self.paths.raw_dir,
            provider=self.provider,
            embedding_client=self.embedding_client if include_embeddings else None,
        ).answer(question, limit=limit)
        if result is None:
            return result
        self._append_history(
            HistoryRecord(
                id=uuid4().hex,
                kind="qa",
                created_at=datetime.now(timezone.utc),
                status=result.status,
                question=question,
                message=result.reason,
            )
        )
        return result

    def synthesize_topic(self, topic: str) -> KnowledgeRecord:
        """Compile all existing Notes for one topic through the Core."""

        return KnowledgeCompiler(
            provider=self.provider,
            knowledge_dir=self.paths.knowledge_dir,
            notes_dir=self.paths.notes_dir,
        ).compile(topic)

    def generate_topics(self, *, limit: int = 5) -> TopicGenerationResult:
        """Generate explainable topic candidates from local persisted data."""

        result = TopicGenerator(
            index_path=self.paths.index_path,
            knowledge_dir=self.paths.knowledge_dir,
            notes_dir=self.paths.notes_dir,
        ).generate(limit=limit)
        self._append_history(
            HistoryRecord(
                id=uuid4().hex,
                kind="topic",
                created_at=datetime.now(timezone.utc),
                status=result.status,
                candidate_titles=[candidate.title for candidate in result.candidates],
                message=result.message,
            )
        )
        return result

    def write_script(
        self,
        selected_topic: TopicCandidate | str | None = None,
        *,
        confirmed: bool = False,
        limit: int = 10,
    ) -> ScriptResult:
        """Write only after confirmation; ScriptWriter performs fresh retrieval."""

        result = ScriptWriter(
            index_path=self.paths.index_path,
            knowledge_dir=self.paths.knowledge_dir,
            notes_dir=self.paths.notes_dir,
            raw_dir=self.paths.raw_dir,
            provider=self.provider,
        ).write(selected_topic, confirmed=confirmed, limit=limit)
        self._append_history(
            HistoryRecord(
                id=uuid4().hex,
                kind="script",
                created_at=datetime.now(timezone.utc),
                status=result.status,
                topic=result.topic,
                script_title=result.title,
                message=result.message,
            )
        )
        return result

    def list_history(self) -> list[HistoryRecord]:
        """Return the current user's operation history in chronological order."""

        return self.history_store.list_records()

    def _append_history(self, record: HistoryRecord) -> None:
        """Persist one history record without silently ignoring storage failures."""

        self.history_store.append(record)


__all__ = [
    "IngestResult",
    "UIPaths",
    "UIService",
    "can_generate_script",
    "find_candidate",
]
