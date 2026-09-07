"""Deterministic keyword extraction used by the V1 index.

The extractor is intentionally small and local.  It is not a language model
and does not claim to identify semantic topics; it only produces stable terms
from the fields already present in a Note.
"""

from collections import Counter
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pkb.notes.model import Note


_TOKEN_RE = re.compile(
    r"[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*|[\u4e00-\u9fff]+",
)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")

# These are deliberately limited to terms that occur frequently as grammar
# or document boilerplate.  Domain terms such as "AI" and "knowledge" stay
# searchable instead of being silently discarded.
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "may",
        "might",
        "more",
        "of",
        "on",
        "or",
        "our",
        "should",
        "that",
        "the",
        "their",
        "there",
        "these",
        "this",
        "those",
        "to",
        "under",
        "was",
        "were",
        "what",
        "when",
        "which",
        "while",
        "who",
        "will",
        "with",
        "would",
        "you",
        "your",
        "document",
        "documents",
        "note",
        "notes",
        "source",
        "sources",
        "summary",
        "content",
        "test",
        "tests",
        "synthetic",
        "的",
        "地",
        "得",
        "是",
        "了",
        "在",
        "和",
        "与",
        "及",
        "或",
        "这",
        "那",
        "一个",
        "可以",
        "需要",
        "通过",
        "用于",
        "以及",
        "进行",
        "主要",
        "相关",
        "内容",
        "资料",
        "文档",
        "来源",
    }
)


def normalize_term(value: str) -> str:
    """Normalize one tag or keyword for case-insensitive comparison."""

    return " ".join(value.casefold().split())


def _cjk_terms(run: str) -> list[str]:
    """Return short deterministic terms from one contiguous CJK run."""

    terms: list[str] = []
    if len(run) <= 4:
        terms.append(run)
    if len(run) >= 2:
        terms.extend(run[index : index + 2] for index in range(len(run) - 1))
    return terms


def tokenize_text(text: str) -> list[str]:
    """Tokenize Latin/numeric text and short CJK terms without external data."""

    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text.casefold()):
        value = match.group(0)
        if _CJK_RE.fullmatch(value):
            tokens.extend(_cjk_terms(value))
        else:
            tokens.append(value)
    return [token for token in tokens if token not in STOPWORDS and _usable(token)]


def _usable(token: str) -> bool:
    if len(token) < 2:
        return False
    return True


def clean_values(values: list[str] | tuple[str, ...]) -> list[str]:
    """Trim and de-duplicate values while preserving their first spelling."""

    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        key = normalize_term(normalized)
        if normalized and key not in seen:
            cleaned.append(normalized)
            seen.add(key)
    return cleaned


def extract_keywords(note: "Note", *, limit: int = 16) -> list[str]:
    """Extract ranked, local keywords from a persisted Note.

    Title terms receive the highest weight, followed by the summary and key
    points.  Quotes and optional user/original text provide lower-weight
    evidence.  The result is stable for the same Note and capped so the JSON
    index stays useful as a lightweight pre-filter.
    """

    if limit <= 0:
        return []

    fields: list[tuple[str, float]] = [(note.title, 4.0), (note.summary, 2.0)]
    fields.extend((value, 2.0) for value in note.key_points)
    fields.extend((value, 1.0) for value in note.quotes)
    if note.original_content:
        fields.append((note.original_content, 1.0))
    if note.user_note:
        fields.append((note.user_note, 0.5))

    scores: Counter[str] = Counter()
    occurrences: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    sequence = 0
    for text, weight in fields:
        for token in tokenize_text(text):
            if token not in first_seen:
                first_seen[token] = sequence
                sequence += 1
            scores[token] += weight
            occurrences[token] += 1

    ranked = sorted(
        scores,
        key=lambda token: (-scores[token], -occurrences[token], first_seen[token], token),
    )
    return ranked[:limit]
