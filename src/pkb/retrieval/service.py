"""Deterministic retrieval over the persisted local JSON Index.

The service deliberately reads only the validated Index.  It does not read
Raw or Note contents, call an AI Provider, create relationships, or use a
vector store.  Those boundaries keep V1 retrieval local and auditable.
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


FIELD_WEIGHTS: Mapping[RetrievalField, float] = {
    "title": 0.45,
    "tags": 0.25,
    "keywords": 0.18,
    "topic": 0.12,
}
RELATED_WEIGHT = 0.10
_DIRECT_FIELDS: tuple[RetrievalField, ...] = ("title", "tags", "keywords", "topic")
_ALL_FIELDS: tuple[RetrievalField, ...] = (*_DIRECT_FIELDS, "related")


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
) -> tuple[list[str], list[RetrievalReason], float]:
    """Score only existing links whose target itself matches the query."""

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
        if not target_matches:
            continue

        target_terms = [
            term
            for field in _DIRECT_FIELDS
            for term in target_matches.get(field, _FieldMatch((), ())).terms
        ]
        coverage = _coverage(target_terms, query)
        link_factor = 0.5 + (0.5 * link.score)
        related_score = RELATED_WEIGHT * coverage * link_factor
        related_ids.append(link.document_id)
        target_values = [
            value
            for field in _DIRECT_FIELDS
            for value in target_matches.get(field, _FieldMatch((), ())).values
        ]
        reasons.append(
            RetrievalReason(
                field="related",
                matches=[link.document_id, *target_values],
                score=round(related_score, 4),
                explanation=(
                    f"existing related link to {link.document_id!r}; "
                    f"target matched {', '.join(target_values)}; "
                    f"link reason: {link.reason}"
                ),
            ),
        )
        contribution += related_score

    # Related is one supporting field, not an unlimited bonus per link.
    # Keep all evidence and scale its explanations to the same total budget.
    if contribution > RELATED_WEIGHT:
        scale = RELATED_WEIGHT / contribution
        reasons = [
            reason.model_copy(update={"score": round(reason.score * scale, 4)})
            for reason in reasons
        ]
        contribution = RELATED_WEIGHT
    return related_ids, reasons, contribution


def score_candidate(
    entry: IndexEntry,
    query: str | ParsedQuery,
    *,
    entries: Mapping[str, IndexEntry] | None = None,
) -> RetrievalCandidate | None:
    """Score one Index entry and return an explainable candidate if matched."""

    parsed = query if isinstance(query, ParsedQuery) else parse_query(query)
    if parsed.is_empty:
        return None

    direct_matches = _direct_matches(entry, parsed)
    reasons: list[RetrievalReason] = []
    evidence_values: dict[str, list[str]] = {field: [] for field in _ALL_FIELDS}
    score = 0.0
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
        score += contribution

    if entries is not None and entry.related:
        related_ids, related_reasons, related_score = _related_matches(
            entry,
            parsed,
            entries,
        )
        if related_ids:
            evidence_values["related"] = related_ids
            reasons.extend(related_reasons)
            score += related_score

    if not reasons:
        return None

    reasons.sort(key=lambda reason: (_ALL_FIELDS.index(reason.field), reason.matches))
    evidence = RetrievalEvidence(**evidence_values)
    return RetrievalCandidate(
        document_id=entry.document_id,
        raw_document_id=entry.document_id,
        title=entry.title,
        score=round(min(1.0, score), 4),
        note_path=entry.note_path,
        evidence=evidence,
        reasons=reasons,
    )


def rank_candidates(
    index: IndexFile,
    query: str | ParsedQuery,
    *,
    limit: int | None = None,
) -> list[RetrievalCandidate]:
    """Return stable, explainably scored candidates from an Index object."""

    if not isinstance(index, IndexFile):
        raise TypeError("index must be an IndexFile")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than zero")

    entries_by_id = {entry.document_id: entry for entry in index.entries}
    candidates = [
        candidate
        for entry in index.entries
        if (candidate := score_candidate(entry, query, entries=entries_by_id))
    ]
    candidates.sort(key=lambda candidate: (-candidate.score, candidate.document_id))
    return candidates if limit is None else candidates[:limit]


def retrieve_from_index(
    index: IndexFile,
    query: str,
    *,
    limit: int | None = 10,
) -> RetrievalResult:
    """Search an already loaded local Index without performing any writes."""

    candidates = rank_candidates(index, query, limit=limit)
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
) -> RetrievalResult:
    """Load a JSON Index if needed, then perform one local retrieval."""

    loaded = read_index(index) if isinstance(index, (str, Path)) else index
    return retrieve_from_index(loaded, query, limit=limit)


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

    def search(self, query: str, *, limit: int | None = 10) -> RetrievalResult:
        """Search the configured Index."""

        return retrieve_from_index(self._load(), query, limit=limit)

    def retrieve(self, query: str, *, limit: int | None = 10) -> RetrievalResult:
        """Alias for ``search`` used by retrieval-oriented callers."""

        return self.search(query, limit=limit)

    def build_candidate_judgment_request(
        self,
        query: str,
        *,
        limit: int | None = 10,
    ) -> CandidateJudgmentRequest:
        """Prepare a future AI boundary without invoking any Provider."""

        result = self.search(query, limit=limit)
        return CandidateJudgmentRequest(
            query=query,
            candidates=result.candidates,
        )


IndexRetriever = RetrievalService
