"""Langfuse SDK singleton for LLM tracing throughout the application."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from webx5.utils.contextvars_utils import user_id_context

if TYPE_CHECKING:
    from langfuse import Langfuse

_log = structlog.get_logger(__name__)
_client: "Langfuse | None" = None


def get_langfuse() -> "Langfuse | None":
    """Return the initialized Langfuse client, or None if unavailable."""
    return _client


def _default_host() -> str:
    """Docker Compose service DNS inside containers; published port on the host."""
    if os.path.exists("/.dockerenv") or os.getenv("CONTAINER", "") == "true":
        return "http://langfuse:3000"
    return "http://localhost:3001"


def init_langfuse(*, force: bool = False) -> "Langfuse | None":
    """Initialize Langfuse SDK. Returns client or None on failure.

    `force=True` rebuilds the client — required after Celery prefork, because
    the parent's background ingestion thread does not survive `fork()`.
    """
    global _client

    if _client is not None and not force:
        return _client

    api_key = os.getenv("LANGFUSE_API_KEY")
    if not api_key:
        _log.warning("langfuse_api_key_missing", message="LANGFUSE_API_KEY not set; LLM tracing disabled")
        _client = None
        return None

    try:
        from langfuse import Langfuse

        host = os.getenv("LANGFUSE_HOST") or _default_host()
        secret_key = os.getenv("LANGFUSE_SECRET_KEY") or ""
        if not secret_key:
            _log.warning(
                "langfuse_secret_key_missing",
                message="LANGFUSE_SECRET_KEY not set; ingestion will be rejected",
            )

        _client = Langfuse(
            public_key=api_key,
            secret_key=secret_key,
            host=host,
            enabled=True,
        )
        _log.info("langfuse_initialized", host=host)
        return _client
    except Exception as exc:
        _log.warning("langfuse_init_failed", error=str(exc), message="LLM tracing disabled")
        _client = None
        return None


@dataclass
class LLMTrace:
    """Active Langfuse generation, or a no-op when the SDK is unavailable."""

    langfuse: Any = None
    generation: Any = None
    start_time: float = field(default_factory=time.monotonic)

    @property
    def duration_ms(self) -> float:
        return round((time.monotonic() - self.start_time) * 1000, 2)

    def end_success(self, output: Any) -> None:
        if self.generation is None:
            return
        try:
            self.generation.end(output=output, metadata={"duration_ms": self.duration_ms})
            self.langfuse.flush()
        except Exception as exc:
            _log.warning("langfuse_generation_end_failed", error=str(exc))

    def end_error(self, exc: BaseException) -> None:
        if self.generation is None:
            return
        try:
            self.generation.end(
                metadata={"duration_ms": self.duration_ms, "error": str(exc)},
                level="ERROR",
            )
            self.langfuse.flush()
        except Exception:
            pass


def start_llm_trace(
    trace_name: str,
    model: str,
    input_data: Any,
    generation_name: str = "openrouter_completion",
    metadata: dict | None = None,
) -> LLMTrace:
    """Begin a Langfuse trace+generation. Never raises; returns a no-op handle if disabled."""
    langfuse = get_langfuse()
    if langfuse is None:
        return LLMTrace()

    extra = {"model": model, **(metadata or {})}
    try:
        trace = langfuse.trace(
            name=trace_name,
            user_id=user_id_context.get(),
            metadata=extra,
        )
        generation = trace.generation(
            name=generation_name,
            model=model,
            input=input_data,
        )
        return LLMTrace(langfuse=langfuse, generation=generation)
    except Exception as exc:
        _log.warning("langfuse_trace_create_failed", error=str(exc))
        return LLMTrace()
