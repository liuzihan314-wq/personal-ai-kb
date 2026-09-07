"""Pluggable AI provider contracts and local test implementations."""

from pkb.providers.mock import MockAIProvider
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
    "ProviderDocument",
    "RelatedLink",
    "TopicSuggestion",
]
