"""Streamlit MVP entry point and its thin Core Service facade."""

from pkb.ui.services import (
    IngestResult,
    UIPaths,
    UIService,
    can_generate_script,
    find_candidate,
)

__all__ = [
    "IngestResult",
    "UIPaths",
    "UIService",
    "can_generate_script",
    "find_candidate",
]
