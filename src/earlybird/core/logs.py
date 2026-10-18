"""Structured logging: readable in a terminal, JSON lines everywhere else."""

import logging
import sys

import structlog

from earlybird.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    use_json = settings.log_format == "json" or (
        settings.log_format == "auto" and not sys.stderr.isatty()
    )
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer() if use_json else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[settings.log_level.upper()]
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
