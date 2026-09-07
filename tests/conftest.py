"""Shared pytest fixtures for isolated settings-based tests."""

import pytest

from pkb.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Keep environment-driven settings isolated between test cases."""

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
