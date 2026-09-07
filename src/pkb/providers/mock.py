"""Deterministic, network-free provider for tests and local development."""

import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

from pkb.providers.protocol import (
    DocumentInput,
    ProviderDocument,
    RelatedLink,
    TopicSuggestion,
)


class MockAIProvider:
    """Implement the provider contract without SDKs, credentials, or I/O.

    ``responses`` can override any operation by name, which lets unit tests
    assert downstream behavior without depending on generated wording.
    """

    def __init__(self, responses: Mapping[str, Any] | None = None) -> None:
        self.calls: list[str] = []
        self._responses = dict(responses or {})

    def _response(self, operation: str, default: Any) -> Any:
        self.calls.append(operation)
        return self._responses.get(operation, default)

    @staticmethod
    def _document(document: DocumentInput) -> ProviderDocument:
        if isinstance(document, ProviderDocument):
            return document
        return ProviderDocument(content=document)

    @staticmethod
    def _sentences(content: str) -> list[str]:
        normalized = " ".join(content.split())
        return [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?。！？])\s*", normalized)
            if sentence.strip()
        ]

    @staticmethod
    def _tokens(content: str) -> set[str]:
        words = re.findall(r"[A-Za-z0-9_][A-Za-z0-9_-]*|[\u4e00-\u9fff]{2,}", content.lower())
        return set(words)

    def summarize(self, document: DocumentInput) -> str:
        item = self._document(document)
        normalized = " ".join(item.content.split())
        default = f"Mock summary: {normalized[:200]}"
        if len(normalized) > 200:
            default += "…"
        return cast(str, self._response("summarize", default))

    def extract_key_points(self, document: DocumentInput) -> list[str]:
        item = self._document(document)
        default = self._sentences(item.content)[:3] or [item.content]
        return cast(list[str], self._response("extract_key_points", default))

    def extract_quotes(self, document: DocumentInput) -> list[str]:
        item = self._document(document)
        quoted = re.findall(r"[\"“「『](.*?)[\"”」』]", item.content)
        default = quoted[:3] or self._sentences(item.content)[:1]
        return cast(list[str], self._response("extract_quotes", default))

    def generate_tags(self, document: DocumentInput) -> list[str]:
        item = self._document(document)
        default = sorted(self._tokens(item.content))[:5]
        return cast(list[str], self._response("generate_tags", default))

    def link_related(
        self,
        document: ProviderDocument,
        candidates: Sequence[ProviderDocument] = (),
    ) -> list[RelatedLink]:
        source_tokens = self._tokens(document.content)
        links: list[RelatedLink] = []
        for index, candidate in enumerate(candidates, start=1):
            overlap = source_tokens & self._tokens(candidate.content)
            if not overlap:
                continue
            document_id = candidate.document_id or candidate.title or f"candidate-{index}"
            links.append(
                RelatedLink(
                    document_id=document_id,
                    score=min(1.0, len(overlap) / max(1, len(source_tokens))),
                    reason=f"shared terms: {', '.join(sorted(overlap))}",
                )
            )
        return cast(list[RelatedLink], self._response("link_related", links))

    def compile_topic(
        self,
        topic: str,
        notes: Sequence[ProviderDocument] = (),
    ) -> str:
        labels = [note.title or note.document_id or "untitled note" for note in notes]
        source_text = "; ".join(labels) or "no notes"
        default = f"Mock compilation for {topic}: {source_text}."
        return cast(str, self._response("compile_topic", default))

    def answer_question(
        self,
        question: str,
        context: Sequence[ProviderDocument] = (),
    ) -> str:
        evidence = context[0].content[:120] if context else "no context"
        default = f"Mock answer to {question}: {evidence}"
        return cast(str, self._response("answer_question", default))

    def generate_topics(
        self,
        context: Sequence[ProviderDocument] = (),
        *,
        limit: int = 3,
    ) -> list[TopicSuggestion]:
        titles = [item.title for item in context if item.title]
        if not titles:
            titles = ["AI productivity"]
        default = [
            TopicSuggestion(title=title, rationale="Derived from local knowledge context.")
            for title in titles[: max(0, limit)]
        ]
        return cast(list[TopicSuggestion], self._response("generate_topics", default))

    def write_script(
        self,
        topic: str,
        context: Sequence[ProviderDocument] = (),
        *,
        target_seconds: int = 150,
    ) -> str:
        evidence = context[0].content[:120] if context else "no context"
        default = f"Mock script about {topic} ({target_seconds}s).\nEvidence: {evidence}"
        return cast(str, self._response("write_script", default))
