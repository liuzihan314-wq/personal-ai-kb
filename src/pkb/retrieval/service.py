"""Explainable hybrid retrieval over the persisted local JSON Index.

The service reads only validated Index metadata. Direct metadata matches,
optional embedding similarity, and bounded Related support keep retrieval
traceable without introducing a vector database.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import log
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


_EMBEDDING_AUTO = object()


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

# Small, explicit vocabulary for the mixed Chinese site/deployment intent seen
# in local searches. Expansion is directional: a query may find equivalent
# wording in an Index field without rewriting or persisting the query.
_QUERY_ALIASES: Mapping[str, tuple[str, ...]] = {
    "网页": ("网站", "站点"),
    "网站": ("网页", "站点"),
    "站点": ("网页", "网站"),
    "部署": ("发布", "上线"),
    "发布": ("部署", "上线"),
    "上线": ("部署", "发布"),
}


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
        overlap = [
            term
            for term in query.terms
            if value_terms.intersection((term, *_QUERY_ALIASES.get(term, ())))
        ]
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


def _coverage(
    matched_terms: Sequence[str],
    query: ParsedQuery,
    term_weights: Mapping[str, float] | None = None,
) -> float:
    if not query.terms:
        return 0.0
    weights = term_weights or {}
    denominator = sum(weights.get(term, 1.0) for term in query.terms)
    numerator = sum(
        weights.get(term, 1.0)
        for term in set(matched_terms)
        if term in query.terms
    )
    return min(1.0, numerator / denominator) if denominator else 0.0


def _query_term_weights(
    query: ParsedQuery,
    entries: Mapping[str, IndexEntry] | None,
) -> dict[str, float]:
    """Discount frequent query terms using metadata document frequency."""

    if not query.terms or not entries:
        return {term: 1.0 for term in query.terms}

    document_frequencies = {term: 0 for term in query.terms}
    for entry in entries.values():
        corpus_terms = {
            term
            for field in _DIRECT_FIELDS
            for value in _field_values(entry, field)
            for term in tokenize_text(value)
        }
        for term in query.terms:
            aliases = (term, *_QUERY_ALIASES.get(term, ()))
            if corpus_terms.intersection(aliases):
                document_frequencies[term] += 1

    corpus_size = len(entries)
    return {
        term: 1.0 + log((corpus_size + 1) / (frequency + 1))
        for term, frequency in document_frequencies.items()
    }


def _coverage_explanation(
    terms: Sequence[str],
    query: ParsedQuery,
    term_weights: Mapping[str, float],
) -> str:
    matched = sorted(set(terms))
    weights = ", ".join(f"{term}={term_weights.get(term, 1.0):.2f}" for term in matched)
    return (
        f"corpus-weighted coverage {_coverage(matched, query, term_weights):.3f}; "
        f"query-term weights: {weights}"
    )


def _related_sort_key(link: RelatedEntry) -> tuple[float, str]:
    return (-link.score, link.document_id)


def _related_matches(
    entry: IndexEntry,
    query: ParsedQuery,
    entries_by_id: Mapping[str, IndexEntry],
    semantic_index: EmbeddingSemanticIndex | None,
    term_weights: Mapping[str, float],
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
        direct_coverage = _coverage(target_terms, query, term_weights)
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

    # Related is one supporting field, not a popularity bonus for entries with
    # many links. Keep all evidence, but bound the combined contribution to the
    # strongest matching link so generic hubs cannot outrank a direct match.
    if contribution:
        budget = min(RELATED_WEIGHT, max(reason.score for reason in reasons))
        scale = min(1.0, budget / contribution)
        bounded_scores = [round(reason.score * scale, 8) for reason in reasons]
        if sum(bounded_scores) > budget:
            for index in range(len(bounded_scores) - 1, -1, -1):
                other_total = sum(
                    score for score_index, score in enumerate(bounded_scores)
                    if score_index != index
                )
                if other_total <= budget:
                    bounded_scores[index] = round(
                        max(0.0, budget - other_total),
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
    term_weights: Mapping[str, float] | None = None,
    semantic_index: EmbeddingSemanticIndex | None = None,
    embedding_client: EmbeddingClient | None | object = _EMBEDDING_AUTO,
) -> RetrievalCandidate | None:
    """Score one Index entry and return an explainable candidate if matched."""

    parsed = query if isinstance(query, ParsedQuery) else parse_query(query)
    if parsed.is_empty:
        return None

    if semantic_index is None and embedding_client is _EMBEDDING_AUTO:
        embedding_client = DashScopeEmbeddingClient.from_environment()
    if (
        semantic_index is None
        and embedding_client is not None
        and embedding_client is not _EMBEDDING_AUTO
    ):
        corpus = tuple(entries.values()) if entries is not None else (entry,)
        if all(candidate.document_id != entry.document_id for candidate in corpus):
            corpus = (*corpus, entry)
        semantic_index = EmbeddingSemanticIndex(corpus, embedding_client)

    if term_weights is None:
        term_weights = _query_term_weights(parsed, entries)

    direct_matches = _direct_matches(entry, parsed)
    reasons: list[RetrievalReason] = []
    evidence_values: dict[str, list[str]] = {field: [] for field in _ALL_FIELDS}
    for field in _DIRECT_FIELDS:
        match = direct_matches.get(field)
        if match is None:
            continue
        coverage = _coverage(match.terms, parsed, term_weights)
        contribution = FIELD_WEIGHTS[field] * coverage
        evidence_values[field] = list(match.values)
        reasons.append(
            RetrievalReason(
                field=field,
                matches=list(match.values),
                score=round(contribution, 4),
                explanation=(
                    f"{field} matched query terms: {', '.join(match.terms)}; "
                    f"{_coverage_explanation(match.terms, parsed, term_weights)}"
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
            term_weights,
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
    embedding_client: EmbeddingClient | None | object = _EMBEDDING_AUTO,
) -> list[RetrievalCandidate]:
    """Return stable, explainably scored candidates from an Index object."""

    if not isinstance(index, IndexFile):
        raise TypeError("index must be an IndexFile")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than zero")

    entries_by_id = {entry.document_id: entry for entry in index.entries}
    parsed = query if isinstance(query, ParsedQuery) else parse_query(query)
    if embedding_client is _EMBEDDING_AUTO:
        embedding_client = DashScopeEmbeddingClient.from_environment()
    semantic_index = (
        EmbeddingSemanticIndex(tuple(index.entries), embedding_client)
        if embedding_client is not None and embedding_client is not _EMBEDDING_AUTO
        else None
    )
    term_weights = _query_term_weights(parsed, entries_by_id)
    candidates = [
        candidate
        for entry in index.entries
        if (
            candidate := score_candidate(
                entry,
                parsed,
                entries=entries_by_id,
                term_weights=term_weights,
                semantic_index=semantic_index,
                embedding_client=embedding_client,
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
    embedding_client: EmbeddingClient | None | object = _EMBEDDING_AUTO,
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
    embedding_client: EmbeddingClient | None | object = _EMBEDDING_AUTO,
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
        raw_dir: str | Path | None = None,
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
        self.raw_dir = Path(raw_dir) if raw_dir is not None else None

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
        embedding_client: EmbeddingClient | None | object = _EMBEDDING_AUTO,
    ) -> RetrievalResult:
        """Search the configured Index."""

        index = self._load()
        result = retrieve_from_index(
            index,
            query,
            limit=None if self.raw_dir is not None else limit,
            embedding_client=embedding_client,
        )
        if self.raw_dir is None:
            return result
        from pkb.retrieval.raw import read_source, source_passages
        from pkb.retrieval.model import RetrievalEvidence, RetrievalReason
        candidates = {candidate.document_id: candidate for candidate in result.candidates}
        for entry in index.entries:
            text = read_source(self.raw_dir, entry.document_id)
            passage, matches = source_passages(text, query)
            if not passage:
                continue
            raw_score = min(0.9, 0.45 + 0.06 * len(matches))
            reason = RetrievalReason(field="raw", matches=matches, score=raw_score,
                                     explanation="原文相关段落匹配；摘要之外的细节也可检索。")
            prior = candidates.get(entry.document_id)
            if prior is not None:
                candidates[entry.document_id] = prior.model_copy(update={
                    "score": max(prior.score, raw_score),
                    "evidence": prior.evidence.model_copy(update={"raw": matches}),
                    "reasons": [*prior.reasons, reason],
                })
            else:
                candidates[entry.document_id] = RetrievalCandidate(
                    document_id=entry.document_id, raw_document_id=entry.document_id,
                    title=entry.title, note_path=entry.note_path, score=raw_score,
                    evidence=RetrievalEvidence(raw=matches), reasons=[reason],
                )
        ranked = sorted(candidates.values(), key=lambda item: (-item.score, item.document_id))
        if limit is not None:
            ranked = ranked[:limit]
        return RetrievalResult(query=query, status="ok" if ranked else "no_hits", candidates=ranked)

    def retrieve(
        self,
        query: str,
        *,
        limit: int | None = 10,
        embedding_client: EmbeddingClient | None | object = _EMBEDDING_AUTO,
    ) -> RetrievalResult:
        """Alias for ``search`` used by retrieval-oriented callers."""

        return self.search(query, limit=limit, embedding_client=embedding_client)

    def build_candidate_judgment_request(
        self,
        query: str,
        *,
        limit: int | None = 10,
        embedding_client: EmbeddingClient | None | object = _EMBEDDING_AUTO,
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
