"""Shared pytest fixtures for isolated settings-based tests."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from pkb.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Keep environment-driven settings isolated between test cases."""

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def tmp_path() -> Path:
    """Override pytest's default tmp_path to stay inside the project worktree.

    The brokered sandbox denies writes under the system temp root for some
    test files, so all test scratch space is created under ``tests/_tmp``.
    """

    base = Path(__file__).parent / "_tmp"
    base.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=base, prefix="pytest-") as directory:
        yield Path(directory)
