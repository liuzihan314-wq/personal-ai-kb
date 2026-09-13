"""Explainable hybrid retrieval over the persisted local JSON Index.

The service reads only validated Index metadata. Direct metadata matches,
optional embedding similarity, and bounded Related support keep retrieval
traceable without introducing a vector database.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pkb.index.keywords import normalize_term, tokenize_text
from pkb.index.model import IndexEntry, IndexFile, RelatedEntry
from pkb.index.storage import read_index
from pkb.retrieval.model import (
    CandidateJudgmentRequest,
    RetrievalCandidate,
    RetrievalEvidence,
    RetrievalField,
    RetrievalReason,
    RetrievalResult,
)
from pkb.retrieval.semantic import (
    SEMANTIC_METHOD,
    DashScopeEmbeddingClient,
    EmbeddingClient,
    EmbeddingSemanticIndex,
)


FIELD_WEIGHTS: Mapping[RetrievalField, float] = {
    "title": 0.30,
    "tags": 0.20,
    "keywords": 0.15,
    "topic": 0.10,
}
SEMANTIC_WEIGHT = 0.15
RELATED_WEIGHT = 0.10
SEMANTIC_MIN_SIMILARITY = 0.08
_DIRECT_FIELDS: tuple[RetrievalField, ...] = ("title", "tags", "keywords", "topic")
_ALL_FIELDS: tuple[RetrievalField, ...] = (*_DIRECT_FIELDS, "semantic", "related")


@dataclass(frozen=True)
class ParsedQuery:
    """Normalized query terms used by the deterministic scorer."""

    raw: str
    terms: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not self.terms


@dataclass(frozen=True)
class _FieldMatch:
    values: tuple[str, ...]
    terms: tuple[str, ...]


def parse_query(query: str) -> ParsedQuery:
    """Parse a query into stable, local-only searchable terms."""

    if not isinstance(query, str):
        raise TypeError("query must be a string")

    terms: list[str] = []
    seen: set[str] = set()
    for term in tokenize_text(query):
        normalized = normalize_term(term)
        if normalized and normalized not in seen:
            terms.append(normalized)
            seen.add(normalized)
    return ParsedQuery(raw=query, terms=tuple(terms))


def _field_values(entry: IndexEntry, field: RetrievalField) -> tuple[str, ...]:
    if field == "topic":
        return (entry.topic,) if entry.topic else ()
    if field == "title":
        return (entry.title,)
    return tuple(getattr(entry, field))


def _match_field(
    entry: IndexEntry,
    field: RetrievalField,
    query: ParsedQuery,
) -> _FieldMatch:
    """Return original field values and query terms that overlap."""

    if query.is_empty:
        return _FieldMatch((), ())

    values: list[str] = []
    matched_terms: list[str] = []
    seen_values: set[str] = set()
    seen_terms: set[str] = set()
    for value in _field_values(entry, field):
        value_terms = set(tokenize_text(value))
        overlap = [term for term in query.terms if term in value_terms]
        if not overlap:
            continue
        value_key = normalize_term(value)
        if value_key not in seen_values:
            values.append(value)
            seen_values.add(value_key)
        for term in overlap:
            if term not in seen_terms:
                matched_terms.append(term)
                seen_terms.add(term)
    return _FieldMatch(tuple(values), tuple(matched_terms))


def _direct_matches(
    entry: IndexEntry,
    query: ParsedQuery,
) -> dict[RetrievalField, _FieldMatch]:
    matches: dict[RetrievalField, _FieldMatch] = {}
    for field in _DIRECT_FIELDS:
        match = _match_field(entry, field, query)
        if match.values:
            matches[field] = match
    return matches


def _coverage(matched_terms: Sequence[str], query: ParsedQuery) -> float:
    if not query.terms:
        return 0.0
    return min(1.0, len(set(matched_terms)) / len(query.terms))


def _related_sort_key(link: RelatedEntry) -> tuple[float, str]:
    return (-link.score, link.document_id)


def _related_matches(
    entry: IndexEntry,
    query: ParsedQuery,
    entries_by_id: Mapping[str, IndexEntry],
    semantic_index: EmbeddingSemanticIndex | None,
) -> tuple[list[str], list[RetrievalReason], float]:
    """Score existing links whose target matches directly or semantically."""

    related_ids: list[str] = []
    reasons: list[RetrievalReason] = []
    contribution = 0.0
    for link in sorted(entry.related, key=_related_sort_key):
        target = entries_by_id.get(link.document_id)
        if target is None:
            # A stale link is not allowed to manufacture a candidate or a
            # relationship; the persisted Index remains the source of truth.
            continue
        target_matches = _direct_matches(target, query)
        target_semantic = (
            semantic_index.match(query.raw, target)
            if semantic_index is not None
            else None
        )
        if not target_matches and (
            target_semantic is None
            or target_semantic.similarity < SEMANTIC_MIN_SIMILARITY
        ):
            continue

        target_terms = [
            term
            for field in _DIRECT_FIELDS
            for term in target_matches.get(field, _FieldMatch((), ())).terms
        ]
        direct_coverage = _coverage(target_terms, query)
        coverage = max(
            direct_coverage,
            target_semantic.similarity if target_semantic is not None else 0.0,
        )
        link_factor = 0.5 + (0.5 * link.score)
        related_score = RELATED_WEIGHT * coverage * link_factor
        related_ids.append(link.document_id)
        target_values = [
            value
            for field in _DIRECT_FIELDS
            for value in target_matches.get(field, _FieldMatch((), ())).values
        ]
        if not target_values:
            target_values = [
                f"semantic features: {', '.join(target_semantic.features)}"
            ]
        target_explanation = (
            f"target matched {', '.join(target_values)}"
            if target_matches
            else (
                f"target semantic similarity {target_semantic.similarity:.4f}; "
                f"model={target_semantic.model}; "
                f"dimension={target_semantic.dimension}; "
                f"represented fields: {', '.join(target_semantic.features)}"
            )
        )
        reasons.append(
            RetrievalReason(
                field="related",
                matches=[link.document_id, *target_values],
                score=related_score,
                explanation=(
                    f"existing related link to {link.document_id!r}; "
                    f"{target_explanation}; "
                    f"link reason: {link.reason}"
                ),
            ),
        )
        contribution += related_score

    # Related is one supporting field, not an unlimited bonus per link.
    # Keep all evidence and scale its explanations to the same total budget.
    if contribution:
        scale = min(1.0, RELATED_WEIGHT / contribution)
        bounded_scores = [round(reason.score * scale, 8) for reason in reasons]
        if sum(bounded_scores) > RELATED_WEIGHT:
            for index in range(len(bounded_scores) - 1, -1, -1):
                other_total = sum(
                    score for score_index, score in enumerate(bounded_scores)
                    if score_index != index
                )
                if other_total <= RELATED_WEIGHT:
                    bounded_scores[index] = round(
                        max(0.0, RELATED_WEIGHT - other_total),
                        8,
                    )
                    break
        reasons = [
            reason.model_copy(update={"score": score})
            for reason, score in zip(reasons, bounded_scores, strict=True)
        ]
        contribution = sum(bounded_scores)
    return related_ids, reasons, contribution


def score_candidate(
    entry: IndexEntry,
    query: str | ParsedQuery,
    *,
    entries: Mapping[str, IndexEntry] | None = None,
    semantic_index: EmbeddingSemanticIndex | None = None,
    embedding_client: EmbeddingClient | None = None,
) -> RetrievalCandidate | None:
    """Score one Index entry and return an explainable candidate if matched."""

    parsed = query if isinstance(query, ParsedQuery) else parse_query(query)
    if parsed.is_empty:
        return None

    if semantic_index is None and embedding_client is None:
        embedding_client = DashScopeEmbeddingClient.from_environment()
    if semantic_index is None and embedding_client is not None:
        corpus = tuple(entries.values()) if entries is not None else (entry,)
        if all(candidate.document_id != entry.document_id for candidate in corpus):
            corpus = (*corpus, entry)
        semantic_index = EmbeddingSemanticIndex(corpus, embedding_client)

    direct_matches = _direct_matches(entry, parsed)
    reasons: list[RetrievalReason] = []
    evidence_values: dict[str, list[str]] = {field: [] for field in _ALL_FIELDS}
    for field in _DIRECT_FIELDS:
        match = direct_matches.get(field)
        if match is None:
            continue
        contribution = FIELD_WEIGHTS[field] * _coverage(match.terms, parsed)
        evidence_values[field] = list(match.values)
        reasons.append(
            RetrievalReason(
                field=field,
                matches=list(match.values),
                score=round(contribution, 4),
                explanation=(
                    f"{field} matched query terms: {', '.join(match.terms)}"
                ),
            ),
        )

    semantic = (
        semantic_index.match(parsed.raw, entry)
        if semantic_index is not None
        else None
    )
    if semantic is not None and semantic.similarity >= SEMANTIC_MIN_SIMILARITY:
        evidence_values["semantic"] = list(semantic.features)
        reasons.append(
            RetrievalReason(
                field="semantic",
                matches=list(semantic.features),
                score=round(SEMANTIC_WEIGHT * semantic.similarity, 4),
                explanation=(
                    f"{SEMANTIC_METHOD} "
                    f"model={semantic.model}; "
                    f"dimension={semantic.dimension}; "
                    f"similarity={semantic.similarity:.4f}; "
                    f"represented fields: {', '.join(semantic.features)}"
                ),
            ),
        )

    if entries is not None and entry.related:
        related_ids, related_reasons, _ = _related_matches(
            entry,
            parsed,
            entries,
            semantic_index,
        )
        if related_ids:
            evidence_values["related"] = related_ids
            reasons.extend(related_reasons)

    if not reasons:
        return None

    reasons.sort(key=lambda reason: (_ALL_FIELDS.index(reason.field), reason.matches))
    evidence = RetrievalEvidence(**evidence_values)
    return RetrievalCandidate(
        document_id=entry.document_id,
        raw_document_id=entry.document_id,
        title=entry.title,
        score=round(min(1.0, sum(reason.score for reason in reasons)), 4),
        note_path=entry.note_path,
        evidence=evidence,
        reasons=reasons,
    )


def rank_candidates(
    index: IndexFile,
    query: str | ParsedQuery,
    *,
    limit: int | None = None,
    embedding_client: EmbeddingClient | None = None,
) -> list[RetrievalCandidate]:
    """Return stable, explainably scored candidates from an Index object."""

    if not isinstance(index, IndexFile):
        raise TypeError("index must be an IndexFile")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than zero")

    entries_by_id = {entry.document_id: entry for entry in index.entries}
    parsed = query if isinstance(query, ParsedQuery) else parse_query(query)
    if embedding_client is None:
        embedding_client = DashScopeEmbeddingClient.from_environment()
    semantic_index = (
        EmbeddingSemanticIndex(tuple(index.entries), embedding_client)
        if embedding_client is not None
        else None
    )
    candidates = [
        candidate
        for entry in index.entries
        if (
            candidate := score_candidate(
                entry,
                parsed,
                entries=entries_by_id,
                semantic_index=semantic_index,
            )
        )
    ]
    candidates.sort(key=lambda candidate: (-candidate.score, candidate.document_id))
    return candidates if limit is None else candidates[:limit]


def retrieve_from_index(
    index: IndexFile,
    query: str,
    *,
    limit: int | None = 10,
    embedding_client: EmbeddingClient | None = None,
) -> RetrievalResult:
    """Search an already loaded local Index without performing any writes."""

    candidates = rank_candidates(
        index,
        query,
        limit=limit,
        embedding_client=embedding_client,
    )
    return RetrievalResult(
        query=query,
        status="ok" if candidates else "no_hits",
        candidates=candidates,
    )


def search_index(
    index: IndexFile | str | Path,
    query: str,
    *,
    limit: int | None = 10,
    embedding_client: EmbeddingClient | None = None,
) -> RetrievalResult:
    """Load a JSON Index if needed, then perform one local retrieval."""

    loaded = read_index(index) if isinstance(index, (str, Path)) else index
    return retrieve_from_index(
        loaded,
        query,
        limit=limit,
        embedding_client=embedding_client,
    )


retrieve = search_index
search = search_index


class RetrievalService:
    """Path-bound facade for deterministic local retrieval."""

    def __init__(
        self,
        index_path: str | Path | IndexFile | None = None,
        *,
        index: IndexFile | None = None,
    ) -> None:
        if index_path is not None and index is not None:
            raise ValueError("provide either index_path or index, not both")
        if isinstance(index_path, IndexFile):
            if index is not None:
                raise ValueError("provide either index_path or index, not both")
            index = index_path
            index_path = None
        if index is None and index_path is None:
            raise ValueError("index_path or index is required")
        self.index_path = Path(index_path) if index_path is not None else None
        self._index = index

    def _load(self) -> IndexFile:
        if self._index is not None:
            return self._index
        assert self.index_path is not None
        return read_index(self.index_path)

    def search(
        self,
        query: str,
        *,
        limit: int | None = 10,
        embedding_client: EmbeddingClient | None = None,
    ) -> RetrievalResult:
        """Search the configured Index."""

        return retrieve_from_index(
            self._load(),
            query,
            limit=limit,
            embedding_client=embedding_client,
        )

    def retrieve(
        self,
        query: str,
        *,
        limit: int | None = 10,
        embedding_client: EmbeddingClient | None = None,
    ) -> RetrievalResult:
        """Alias for ``search`` used by retrieval-oriented callers."""

        return self.search(query, limit=limit, embedding_client=embedding_client)

    def build_candidate_judgment_request(
        self,
        query: str,
        *,
        limit: int | None = 10,
        embedding_client: EmbeddingClient | None = None,
    ) -> CandidateJudgmentRequest:
        """Prepare a future AI boundary without invoking any Provider."""

        result = self.search(
            query,
            limit=limit,
            embedding_client=embedding_client,
        )
        return CandidateJudgmentRequest(
            query=query,
            candidates=result.candidates,
        )


IndexRetriever = RetrievalService
