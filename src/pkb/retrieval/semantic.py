"""Embedding-backed semantic similarity for local Index retrieval.

The production implementation uses an injected embedding client. The default
client is a small standard-library HTTP adapter for Alibaba Cloud Model
Studio's OpenAI-compatible embeddings endpoint; no SDK, model, or local
vector database is required. Offline tests inject fixed vectors.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
import math
import os
import ssl
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pkb.index.model import IndexEntry

try:
    import certifi
except ImportError:  # pragma: no cover - only used on minimal runtimes
    certifi = None


SEMANTIC_METHOD = "text_embedding_cosine"
DEFAULT_EMBEDDING_MODEL = "qwen3.7-text-embedding-flash"


class EmbeddingRequestError(RuntimeError):
    """Raised when the embedding service rejects or cannot complete a request."""


EmbeddingVector = tuple[float, ...]
EmbeddingTransport = Callable[
    [str, Mapping[str, str], Mapping[str, object]],
    Mapping[str, object],
]


class EmbeddingClient(Protocol):
    """Minimal client contract used by the retrieval layer."""

    model: str

    def embed(self, texts: Sequence[str]) -> Sequence[EmbeddingVector]:
        """Return one vector for each input text, in the same order."""


class DashScopeEmbeddingClient:
    """Call Alibaba Cloud Model Studio's OpenAI-compatible embeddings API."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_EMBEDDING_MODEL,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 60.0,
        transport: EmbeddingTransport | None = None,
    ) -> None:
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        if not self.model or not self.base_url or not self.api_key:
            raise ValueError("model, base_url, and api_key are required")

    @property
    def endpoint(self) -> str:
        suffix = "/embeddings"
        return self.base_url if self.base_url.endswith(suffix) else self.base_url + suffix

    def _default_transport(
        self,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, object],
    ) -> Mapping[str, object]:
        request = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=dict(headers),
            method="POST",
        )
        try:
            ssl_context = ssl.create_default_context(
                cafile=certifi.where() if certifi is not None else None,
            )
            with urlopen(  # noqa: S310
                request,
                timeout=self.timeout_seconds,
                context=ssl_context,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise EmbeddingRequestError(
                f"Embedding service returned HTTP {exc.code}: {detail}"
            ) from exc
        except (URLError, TimeoutError, UnicodeError, json.JSONDecodeError) as exc:
            raise EmbeddingRequestError("Embedding service request failed") from exc
        if not isinstance(payload, Mapping):
            raise EmbeddingRequestError("Embedding service returned a non-object response")
        return payload

    def embed(self, texts: Sequence[str]) -> list[EmbeddingVector]:
        values = [text for text in texts]
        if not values:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in values):
            raise ValueError("embedding texts must be non-empty strings")

        body: dict[str, object] = {"model": self.model, "input": values}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = (self._transport or self._default_transport)(
            self.endpoint,
            headers,
            body,
        )
        raw_data = payload.get("data")
        if not isinstance(raw_data, list):
            raise EmbeddingRequestError("Embedding response has no data list")

        indexed: dict[int, EmbeddingVector] = {}
        for item in raw_data:
            if not isinstance(item, Mapping):
                raise EmbeddingRequestError("Embedding response contains an invalid item")
            index = item.get("index")
            raw_embedding = item.get("embedding")
            if not isinstance(index, int) or not isinstance(raw_embedding, list):
                raise EmbeddingRequestError("Embedding response item is incomplete")
            try:
                vector = tuple(float(value) for value in raw_embedding)
            except (TypeError, ValueError) as exc:
                raise EmbeddingRequestError("Embedding response contains invalid values") from exc
            if not vector or not all(math.isfinite(value) for value in vector):
                raise EmbeddingRequestError("Embedding response contains an invalid vector")
            indexed[index] = vector

        if set(indexed) != set(range(len(values))):
            raise EmbeddingRequestError("Embedding response indexes do not match the request")
        result = [indexed[index] for index in range(len(values))]
        dimension = len(result[0])
        if any(len(vector) != dimension for vector in result):
            raise EmbeddingRequestError("Embedding response vectors have different dimensions")
        return result

    @classmethod
    def from_environment(cls) -> "DashScopeEmbeddingClient | None":
        """Build a client only when all required runtime settings are present."""

        api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
        base_url = (
            os.getenv("PKB_EMBEDDING_BASE_URL", "").strip()
            or os.getenv("DASHSCOPE_API_BASE", "").strip()
            or os.getenv("DASHSCOPE_API_HOST", "").strip()
        )
        if not api_key or not base_url:
            return None
        return cls(
            model=os.getenv("PKB_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
            base_url=base_url,
            api_key=api_key,
        )


def _entry_embedding_text(entry: IndexEntry) -> str:
    """Represent only searchable Index metadata, never local document content."""

    sections = [f"title: {entry.title}"]
    if entry.tags:
        sections.append(f"tags: {', '.join(entry.tags)}")
    if entry.keywords:
        sections.append(f"keywords: {', '.join(entry.keywords)}")
    if entry.topic:
        sections.append(f"topic: {entry.topic}")
    return "\n".join(sections)


def _cosine_similarity(left: EmbeddingVector, right: EmbeddingVector) -> float:
    if len(left) != len(right) or not left or not right:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


@dataclass(frozen=True)
class SemanticMatch:
    """A vector similarity result with traceable input metadata."""

    similarity: float
    features: tuple[str, ...] = ()
    model: str = ""
    dimension: int = 0

    @property
    def score(self) -> float:
        """Compatibility name for callers using score terminology."""

        return self.similarity


class EmbeddingSemanticIndex:
    """Embed Index metadata once and compare queries with cosine similarity."""

    def __init__(
        self,
        entries: Sequence[IndexEntry],
        client: EmbeddingClient,
        *,
        batch_size: int = 20,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        self.model = client.model
        self._client = client
        self._vectors: dict[str, EmbeddingVector] = {}
        self._entry_features: dict[str, tuple[str, ...]] = {}
        self._query_vectors: dict[str, EmbeddingVector] = {}

        values = tuple(entries)
        texts = [_entry_embedding_text(entry) for entry in values]
        for start in range(0, len(values), batch_size):
            batch_entries = values[start:start + batch_size]
            batch_vectors = client.embed(texts[start:start + batch_size])
            if len(batch_vectors) != len(batch_entries):
                raise EmbeddingRequestError(
                    "embedding client returned an unexpected vector count"
                )
            for entry, vector in zip(batch_entries, batch_vectors, strict=True):
                self._vectors[entry.document_id] = tuple(vector)
                self._entry_features[entry.document_id] = self._features(entry)

    @staticmethod
    def _features(entry: IndexEntry) -> tuple[str, ...]:
        values = [f"title: {entry.title}"]
        values.extend(f"tag: {value}" for value in entry.tags)
        values.extend(f"keyword: {value}" for value in entry.keywords)
        if entry.topic:
            values.append(f"topic: {entry.topic}")
        return tuple(values[:8])

    def _query_vector(self, query: str) -> EmbeddingVector:
        if query not in self._query_vectors:
            vectors = self._client.embed([query])
            if len(vectors) != 1:
                raise EmbeddingRequestError(
                    "embedding client returned an unexpected query vector count"
                )
            self._query_vectors[query] = tuple(vectors[0])
        return self._query_vectors[query]

    def match(self, query: str, entry: IndexEntry) -> SemanticMatch:
        """Return vector cosine similarity and the metadata represented."""

        vector = self._vectors.get(entry.document_id)
        if vector is None:
            vectors = self._client.embed([_entry_embedding_text(entry)])
            if len(vectors) != 1:
                raise EmbeddingRequestError(
                    "embedding client returned an unexpected entry vector count"
                )
            vector = tuple(vectors[0])
        similarity = _cosine_similarity(self._query_vector(query), vector)
        return SemanticMatch(
            similarity=round(similarity, 8),
            features=self._entry_features.get(entry.document_id, self._features(entry)),
            model=self.model,
            dimension=len(vector),
        )


def semantic_match(
    query: str,
    entry: IndexEntry,
    *,
    entries: Sequence[IndexEntry],
    client: EmbeddingClient,
) -> SemanticMatch:
    """Calculate one embedding-backed semantic match."""

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    return EmbeddingSemanticIndex(entries, client).match(query, entry)


def semantic_similarity(
    query: str,
    entry: IndexEntry,
    *,
    entries: Sequence[IndexEntry],
    client: EmbeddingClient,
) -> float:
    """Return only the embedding cosine similarity value."""

    return semantic_match(query, entry, entries=entries, client=client).similarity
