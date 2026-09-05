"""Capture the raw LLM prompt/response for audit logging (FR-018).

`synth.challenges.call_openrouter` is a module-level function; we don't
modify it. Instead, we monkey-patch it inside a context manager that
records the last call's inputs+outputs, then restore the original.

Compatible with `synth`-package "do not modify" rule from the project.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import synth.challenges as synth_challenges

from webx5.core.langfuse_client import start_llm_trace
from webx5.utils.metrics import LLM_GENERATION_FAILED, LLM_GENERATION_SUCCESS


@contextmanager
def capture_openrouter_io():
    """Yields a mutable dict with the last capture:
    {"system": str, "user": str, "response": str, "error": str | None}.
    Empty until a call occurs.
    """
    captured: dict[str, Any] = {}
    original = synth_challenges.call_openrouter

    def wrapper(model: str, system: str, user: str, api_key: str | None = None, timeout: float = 60.0, max_retries: int = 3):
        captured["system"] = system
        captured["user"] = user
        captured["response"] = None
        captured["error"] = None
        llm_trace = start_llm_trace(
            "challenge_generation",
            model,
            {"system": system, "user": user},
        )
        try:
            response = original(model, system, user, api_key, timeout=timeout, max_retries=max_retries)
            captured["response"] = response
            LLM_GENERATION_SUCCESS.labels(model=model).inc()
            llm_trace.end_success(response)
            return response
        except Exception as e:  # noqa: BLE001
            captured["error"] = str(e)
            LLM_GENERATION_FAILED.labels(model=model, error_type=type(e).__name__).inc()
            llm_trace.end_error(e)
            raise

    synth_challenges.call_openrouter = wrapper
    try:
        yield captured
    finally:
        synth_challenges.call_openrouter = original
