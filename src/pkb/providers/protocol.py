"""Vendor-neutral contracts shared by AI-backed application services."""

from collections.abc import Sequence
from typing import Protocol, TypeAlias, runtime_checkable

from pydantic import BaseModel, Field


class ProviderDocument(BaseModel):
    """Text and optional traceability fields passed to a provider."""

    content: str = Field(min_length=1)
    document_id: str | None = None
    title: str | None = None
    source: str | None = None


DocumentInput: TypeAlias = str | ProviderDocument


class RelatedLink(BaseModel):
    """An explainable relation returned for a candidate document."""

    document_id: str
    score: float = Field(ge=0.0, le=1.0)
    reason: str | None = None


class TopicSuggestion(BaseModel):
    """A topic candidate with a short explanation for later user selection."""

    title: str = Field(min_length=1)
    rationale: str = ""


@runtime_checkable
class AIProvider(Protocol):
    """Stable, vendor-neutral surface for all V1 semantic operations."""

    def summarize(self, document: DocumentInput) -> str:
        """Return a concise summary of one document."""

    def extract_key_points(self, document: DocumentInput) -> list[str]:
        """Return the document's key points in source order."""

    def extract_quotes(self, document: DocumentInput) -> list[str]:
        """Return notable expressions that can be retained or cited."""

    def generate_tags(self, document: DocumentInput) -> list[str]:
        """Return normalized tags for one document."""

    def link_related(
        self,
        document: ProviderDocument,
        candidates: Sequence[ProviderDocument] = (),
    ) -> list[RelatedLink]:
        """Return explainable links from one document to candidate documents."""

    def compile_topic(
        self,
        topic: str,
        notes: Sequence[ProviderDocument] = (),
    ) -> str:
        """Compile several notes into a topic-level knowledge summary."""

    def answer_question(
        self,
        question: str,
        context: Sequence[ProviderDocument] = (),
    ) -> str:
        """Answer a question using the supplied knowledge context."""

    def generate_topics(
        self,
        context: Sequence[ProviderDocument] = (),
        *,
        limit: int = 3,
    ) -> list[TopicSuggestion]:
        """Generate topic candidates from the supplied knowledge context."""

    def write_script(
        self,
        topic: str,
        context: Sequence[ProviderDocument] = (),
        *,
        target_seconds: int = 150,
    ) -> str:
        """Write a spoken script grounded in the supplied context."""
