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

    default_message = (
        "未配置 AI Provider。请在侧栏填写 Provider、模型、endpoint 和 API Key，"
        "或在 .env 中设置 PKB_AI_PROVIDER、PKB_AI_MODEL、PKB_AI_BASE_URL 和 "
        "PKB_AI_API_KEY。"
    )

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message

    def _raise(self) -> None:
        raise ProviderNotConfiguredError(self.message)

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


def provider_from_values(
    provider_name: str | None,
    model: str | None,
    base_url: str | None,
    api_key: str | None,
) -> AIProvider:
    """Create a provider from ephemeral UI values or persisted settings."""

    name = (provider_name or "").strip().casefold()
    normalized_model = (model or "").strip()
    normalized_base_url = (base_url or "").strip()
    normalized_key = (api_key or "").strip()
    if name not in {"deepseek", "openai-compatible"}:
        return UnconfiguredProvider("只支持 DeepSeek 或 OpenAI-compatible Provider。")
    if not normalized_model or not normalized_base_url or not normalized_key:
        return UnconfiguredProvider()
    return OpenAICompatibleProvider(
        model=normalized_model,
        base_url=normalized_base_url,
        api_key=normalized_key,
    )


def configured_provider(settings: Settings | None = None) -> AIProvider:
    """Create the configured provider or an explicit unavailable provider."""

    configured = settings or get_settings()
    key = configured.ai_api_key.get_secret_value() if configured.ai_api_key else ""
    return provider_from_values(
        configured.ai_provider,
        configured.ai_model,
        configured.ai_base_url,
        key,
    )
