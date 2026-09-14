"""Run the metadata-only synthetic WeChat macOS POC.

Usage from the project root::

    uv run python -m scripts.wechat_macos_poc.probe

The probe contains only synthetic labels and metadata.  It never reads a
file, starts WeChat, calls a network endpoint, or writes a result.
"""

import json
from typing import Any

from .classifier import classify_metadata


SYNTHETIC_CASES: tuple[tuple[str, dict[str, Any]], ...] = (
    (
        "official_account_article",
        {
            "item_id": "synthetic-article-001",
            "source_type": "wechat",
            "publisher_type": "official_account",
            "content_type": "article",
            "url": "https://mp.weixin.qq.com/s/synthetic-article-001",
        },
    ),
    (
        "video",
        {
            "item_id": "synthetic-video-001",
            "source_type": "wechat",
            "publisher_type": "official_account",
            "content_type": "video",
            "url": "https://mp.weixin.qq.com/s/synthetic-video-001",
        },
    ),
    (
        "video_account",
        {
            "item_id": "synthetic-video-account-001",
            "source_type": "wechat",
            "publisher_type": "video_account",
            "content_type": "video",
            "url": "https://channels.weixin.qq.com/synthetic-video-account-001",
        },
    ),
    (
        "ordinary_url",
        {
            "item_id": "synthetic-url-001",
            "source_type": "wechat",
            "publisher_type": "unknown",
            "content_type": "url",
            "url": "https://example.invalid/synthetic-url-001",
        },
    ),
    (
        "ambiguous_article",
        {
            "item_id": "synthetic-ambiguous-001",
            "source_type": "wechat",
            "publisher_type": "unknown",
            "content_type": "article",
            "url": "https://mp.weixin.qq.com/s/synthetic-ambiguous-001",
        },
    ),
)


def run_synthetic_probe() -> dict[str, object]:
    """Return deterministic decisions for the synthetic cases."""

    cases = [
        {
            "case": label,
            "decision": decision.decision.value,
            "reason": decision.reason,
        }
        for label, metadata in SYNTHETIC_CASES
        for decision in [classify_metadata(metadata)]
    ]
    accepted_cases = [case["case"] for case in cases if case["decision"] == "accept_candidate"]
    return {
        "accepted_case_names": accepted_cases,
        "accepted_count": len(accepted_cases),
        "case_count": len(cases),
        "cases": cases,
    }


def main() -> None:
    """Print only synthetic classification results."""

    print(json.dumps(run_synthetic_probe(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
