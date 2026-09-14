"""Conservative classification rules for a future WeChat observation adapter.

This module does not access WeChat, the filesystem, a network, or article
content.  It accepts only normalized metadata supplied by a caller.  The
normalized shape is a POC contract, not a claim about undocumented WeChat
native fields.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping
from urllib.parse import urlsplit


class Decision(StrEnum):
    """Possible outcomes for one metadata observation."""

    ACCEPT_CANDIDATE = "accept_candidate"
    REJECT = "reject"
    REVIEW = "review"


@dataclass(frozen=True)
class Classification:
    """A content decision without retaining any content or URL."""

    decision: Decision
    reason: str

    @property
    def accepted(self) -> bool:
        """Return whether the observation may become an ingest candidate."""

        return self.decision is Decision.ACCEPT_CANDIDATE


_FORBIDDEN_CONTENT_TYPES = frozenset(
    {
        "video",
        "video_account",
        "image",
        "audio",
        "mini_program",
        "file",
        "chat_record",
        "url",
    }
)
_FORBIDDEN_PUBLISHER_TYPES = frozenset({"video_account"})
_ARTICLE_PATH = "/s"
_ARTICLE_HOST = "mp.weixin.qq.com"


def _value(metadata: Mapping[str, object], key: str) -> str:
    value = metadata.get(key)
    return value.strip().lower() if isinstance(value, str) else ""


def _text(metadata: Mapping[str, object], key: str) -> str:
    value = metadata.get(key)
    return value.strip() if isinstance(value, str) else ""


def _is_article_url(url: str) -> bool:
    if not url:
        return False

    parsed = urlsplit(url)
    path = parsed.path.rstrip("/")
    return (
        parsed.scheme == "https"
        and parsed.hostname == _ARTICLE_HOST
        and (path == _ARTICLE_PATH or path.startswith(f"{_ARTICLE_PATH}/"))
    )


def classify_metadata(metadata: Mapping[str, object]) -> Classification:
    """Classify normalized metadata using a deny-by-default allowlist.

    A candidate is accepted only when all of the following are explicit:

    * ``source_type`` is ``wechat``;
    * ``publisher_type`` is ``official_account``;
    * ``content_type`` is ``article``;
    * the URL is an HTTPS ``mp.weixin.qq.com/s`` article URL; and
    * ``item_id`` is present for future deduplication.

    No URL is fetched and no metadata is persisted.
    """

    source_type = _value(metadata, "source_type")
    publisher_type = _value(metadata, "publisher_type")
    content_type = _value(metadata, "content_type")
    item_id = _text(metadata, "item_id")
    url = _text(metadata, "url")

    if source_type != "wechat":
        return Classification(Decision.REJECT, "not_wechat_source")

    if content_type in _FORBIDDEN_CONTENT_TYPES:
        return Classification(Decision.REJECT, "forbidden_content_type")

    if publisher_type in _FORBIDDEN_PUBLISHER_TYPES:
        return Classification(Decision.REJECT, "forbidden_publisher_type")

    if content_type != "article":
        return Classification(Decision.REVIEW, "unrecognized_content_type")

    if publisher_type != "official_account":
        return Classification(Decision.REVIEW, "missing_official_account_marker")

    if not _is_article_url(url):
        return Classification(Decision.REVIEW, "unsupported_article_url")

    if not item_id:
        return Classification(Decision.REVIEW, "missing_stable_item_id")

    return Classification(Decision.ACCEPT_CANDIDATE, "explicit_official_account_article")


def is_new_candidate(metadata: Mapping[str, object], seen_ids: set[str]) -> bool:
    """Return whether an accepted item ID is absent from a caller-owned set.

    The function intentionally does not mutate ``seen_ids``.  Persistent
    restart-safe state is outside this POC because no real WeChat observation
    or knowledge-base integration is allowed here.
    """

    classification = classify_metadata(metadata)
    item_id = _text(metadata, "item_id")
    return classification.accepted and bool(item_id) and item_id not in seen_ids
