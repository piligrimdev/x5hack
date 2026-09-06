import logging
import os
from pathlib import Path

import structlog


def default_log_dir() -> Path:
    return Path(os.getenv("LOG_DIR", "/tmp/webx5/logs"))


def configure_logging() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_service_name,
    ]

    # Use JSON renderer unless explicitly in dev console mode
    log_format = os.getenv("LOG_FORMAT", "json" if _running_in_container() else "console")
    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
        context_class=dict,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)


def _running_in_container() -> bool:
    return os.path.exists("/.dockerenv") or os.getenv("CONTAINER", "") == "true"


def _add_service_name(logger, method, event_dict):  # noqa: ANN001
    event_dict.setdefault("service_name", os.getenv("SERVICE_NAME", "webx5"))
    return event_dict
