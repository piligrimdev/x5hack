"""Capture the raw LLM prompt/response for audit logging (FR-018).

`synth.challenges.call_openrouter` is a module-level function; we don't
modify it. Instead, we monkey-patch it inside a context manager that
records the last call's inputs+outputs, then restore the original.

Compatible with `synth`-package "do not modify" rule from the project.
"""

from __future__ import annotations

from contextlib import contextmanager
from threading import Lock
from typing import Any

import synth.challenges as synth_challenges

from webx5.core.langfuse_client import start_llm_trace
from webx5.utils.metrics import LLM_GENERATION_FAILED, LLM_GENERATION_SUCCESS

_patch_lock = Lock()
_patch_depth = 0
_original_call_openrouter = None


def _challenge_llm_input(system: str, user: str) -> list[dict[str, str]]:
    """OpenAI-style messages so Langfuse renders a chat completion, not a raw dict."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


@contextmanager
def capture_openrouter_io():
    """Yields a mutable dict with the last capture:
    {"system": str, "user": str, "response": str, "error": str | None}.
    Empty until a call occurs.

    The patch is refcounted so overlapping `generate_batch` calls in one
    process (threads pool) do not restore `call_openrouter` out from under
    each other and drop Langfuse wrapping mid-request.
    """
    global _patch_depth, _original_call_openrouter
    captured: dict[str, Any] = {}

    def wrapper(
        model: str,
        system: str,
        user: str,
        api_key: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
    ):
        captured["system"] = system
        captured["user"] = user
        captured["response"] = None
        captured["error"] = None
        llm_trace = start_llm_trace(
            "challenge_generation",
            model,
            _challenge_llm_input(system, user),
            generation_name="challenge_generation",
            metadata={"source": "challenges"},
        )
        try:
            original = _original_call_openrouter
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

    with _patch_lock:
        if _patch_depth == 0:
            _original_call_openrouter = synth_challenges.call_openrouter
            synth_challenges.call_openrouter = wrapper
        _patch_depth += 1
    try:
        yield captured
    finally:
        with _patch_lock:
            _patch_depth -= 1
            if _patch_depth == 0:
                synth_challenges.call_openrouter = _original_call_openrouter
                _original_call_openrouter = None
