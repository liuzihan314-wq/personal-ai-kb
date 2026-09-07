import logging

from pkb.logging_config import configure_logging


def test_configure_logging_sets_known_level():
    effective_level = configure_logging("debug")

    assert effective_level == logging.DEBUG
    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_falls_back_for_unknown_level():
    effective_level = configure_logging("not-a-level")

    assert effective_level == logging.INFO
    assert logging.getLogger().level == logging.INFO
