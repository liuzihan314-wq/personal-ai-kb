"""Explainable pairwise related-document scoring for the V1 index."""

from collections.abc import Iterable

from pkb.index.keywords import normalize_term, tokenize_text
from pkb.index.model import IndexEntry, RelatedEntry, RelatedReason


DEFAULT_RELATED_THRESHOLD = 0.45


def _shared_values(left: Iterable[str], right: Iterable[str]) -> list[str]:
    right_values = {normalize_term(value) for value in right if normalize_term(value)}
    return sorted(
        {
            normalize_term(value)
            for value in left
            if normalize_term(value) and normalize_term(value) in right_values
        }
    )


def _title_terms(title: str) -> list[str]:
    return sorted(set(tokenize_text(title)))


def _reason_text(reasons: list[RelatedReason]) -> str:
    labels = {
        "shared_tags": "shared tags",
        "shared_keywords": "shared keywords",
        "shared_title_words": "shared title words",
    }
    return "; ".join(
        f"{labels.get(reason.rule, reason.rule)}: {', '.join(reason.matches)}"
        for reason in reasons
    )


def score_related(
    left: IndexEntry,
    right: IndexEntry,
    *,
    threshold: float = DEFAULT_RELATED_THRESHOLD,
) -> RelatedEntry | None:
    """Return a link when deterministic evidence reaches ``threshold``.

    A single shared explicit tag is strong evidence.  Keywords and title
    words need multiple matches before they can create a link, which keeps
    generic one-word overlap from producing false relationships.
    """

    if left.document_id == right.document_id:
        return None
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("related threshold must be between 0 and 1")

    shared_tags = _shared_values(left.tags, right.tags)
    shared_keywords = _shared_values(left.keywords, right.keywords)
    shared_title_words = _shared_values(_title_terms(left.title), _title_terms(right.title))

    reasons: list[RelatedReason] = []
    score = 0.0
    if shared_tags:
        weight = min(0.95, 0.65 + 0.15 * (len(shared_tags) - 1))
        reasons.append(
            RelatedReason(rule="shared_tags", matches=shared_tags, weight=weight),
        )
        score += weight
    if shared_keywords:
        weight = min(0.45, 0.15 * len(shared_keywords))
        reasons.append(
            RelatedReason(rule="shared_keywords", matches=shared_keywords, weight=weight),
        )
        score += weight
    if shared_title_words:
        weight = min(0.5, 0.25 * len(shared_title_words))
        reasons.append(
            RelatedReason(
                rule="shared_title_words",
                matches=shared_title_words,
                weight=weight,
            ),
        )
        score += weight

    # Keep the evidence floor explicit as well as the numeric threshold.  It
    # prevents a future weight tweak from making one weak term sufficient.
    sufficient_evidence = bool(shared_tags) or len(shared_keywords) >= 3 or len(
        shared_title_words
    ) >= 2
    score = round(min(1.0, score), 4)
    if not reasons or not sufficient_evidence or score < threshold:
        return None

    return RelatedEntry(
        document_id=right.document_id,
        score=score,
        reason=_reason_text(reasons),
        reasons=reasons,
    )


def build_related_map(
    entries: list[IndexEntry],
    *,
    threshold: float = DEFAULT_RELATED_THRESHOLD,
) -> dict[str, list[RelatedEntry]]:
    """Build a symmetric map of directed related links for all entries."""

    links = {entry.document_id: [] for entry in entries}
    for left_index, left in enumerate(entries):
        for right in entries[left_index + 1 :]:
            link = score_related(left, right, threshold=threshold)
            if link is None:
                continue
            links[left.document_id].append(link)
            links[right.document_id].append(
                link.model_copy(update={"document_id": left.document_id}),
            )

    for document_id in links:
        links[document_id].sort(key=lambda link: (-link.score, link.document_id))
    return links


build_related = build_related_map
related_score = score_related
