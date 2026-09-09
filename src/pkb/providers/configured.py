"""Runtime provider selection for the local application UI."""

from collections.abc import Sequence

from pkb.config import Settings, get_settings
from pkb.providers.openai_compatible import OpenAICompatibleProvider
from pkb.providers.protocol import (
    AIProvider,
    DocumentInput,
    ProviderDocument,
    RelatedLink,
    TopicSuggestion,
)


class ProviderNotConfiguredError(RuntimeError):
    """Raised when a semantic UI action needs an unconfigured AI provider."""


class UnconfiguredProvider:
    """Make missing credentials explicit instead of returning Mock output."""

    message = (
        "未配置 AI Provider。请在 .env 中设置 PKB_AI_PROVIDER、PKB_AI_MODEL、"
        "PKB_AI_BASE_URL 和 PKB_AI_API_KEY 后重启应用。"
    )

    @staticmethod
    def _raise() -> None:
        raise ProviderNotConfiguredError(UnconfiguredProvider.message)

    def summarize(self, document: DocumentInput) -> str:
        self._raise()

    def extract_key_points(self, document: DocumentInput) -> list[str]:
        self._raise()

    def extract_quotes(self, document: DocumentInput) -> list[str]:
        self._raise()

    def generate_tags(self, document: DocumentInput) -> list[str]:
        self._raise()

    def link_related(
        self,
        document: ProviderDocument,
        candidates: Sequence[ProviderDocument] = (),
    ) -> list[RelatedLink]:
        self._raise()

    def compile_topic(
        self,
        topic: str,
        notes: Sequence[ProviderDocument] = (),
    ) -> str:
        self._raise()

    def answer_question(
        self,
        question: str,
        context: Sequence[ProviderDocument] = (),
    ) -> str:
        self._raise()

    def generate_topics(
        self,
        context: Sequence[ProviderDocument] = (),
        *,
        limit: int = 3,
    ) -> list[TopicSuggestion]:
        self._raise()

    def write_script(
        self,
        topic: str,
        context: Sequence[ProviderDocument] = (),
        *,
        target_seconds: int = 150,
    ) -> str:
        self._raise()


def configured_provider(settings: Settings | None = None) -> AIProvider:
    """Create the configured provider or an explicit unavailable provider."""

    configured = settings or get_settings()
    name = (configured.ai_provider or "").strip().casefold()
    key = configured.ai_api_key.get_secret_value() if configured.ai_api_key else ""
    if name not in {"deepseek", "openai-compatible"}:
        return UnconfiguredProvider()
    if not configured.ai_model or not configured.ai_base_url or not key:
        return UnconfiguredProvider()
    return OpenAICompatibleProvider(
        model=configured.ai_model,
        base_url=configured.ai_base_url,
        api_key=key,
    )
