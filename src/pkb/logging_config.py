"""Central logging setup for the CLI and future application services."""

import logging


DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: str = "INFO") -> int:
    """Configure stderr logging and return the effective numeric level.

    Unknown levels fall back to ``INFO`` so a typo in a local setting cannot
    prevent the health check from starting.
    """

    candidate = getattr(logging, level.upper(), logging.INFO)
    effective_level = candidate if isinstance(candidate, int) else logging.INFO
    logging.basicConfig(
        level=effective_level,
        format=DEFAULT_LOG_FORMAT,
        force=True,
    )
    return effective_level
