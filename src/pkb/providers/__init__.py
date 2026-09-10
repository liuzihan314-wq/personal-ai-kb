"""Pluggable AI provider contracts and local test implementations."""

from pkb.providers.configured import (
    ProviderNotConfiguredError,
    UnconfiguredProvider,
    configured_provider,
    provider_from_values,
)
from pkb.providers.mock import MockAIProvider
from pkb.providers.openai_compatible import OpenAICompatibleProvider, ProviderRequestError
from pkb.providers.protocol import (
    AIProvider,
    DocumentInput,
    ProviderDocument,
    RelatedLink,
    TopicSuggestion,
)

__all__ = [
    "AIProvider",
    "DocumentInput",
    "MockAIProvider",
    "OpenAICompatibleProvider",
    "ProviderNotConfiguredError",
    "ProviderRequestError",
    "ProviderDocument",
    "RelatedLink",
    "TopicSuggestion",
    "UnconfiguredProvider",
    "configured_provider",
    "provider_from_values",
]
