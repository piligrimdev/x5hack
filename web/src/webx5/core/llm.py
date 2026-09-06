from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

import httpx
import structlog

from webx5.core.langfuse_client import start_llm_trace
from webx5.utils.contextvars_utils import user_id_context

_log = structlog.get_logger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class ToolCall:
    name: str
    arguments: dict = field(default_factory=dict)


def call_openrouter_tools(
    model: str,
    system: str,
    user: str,
    tools: list[dict],
    api_key: str | None = None,
    timeout: float = 30.0,
    max_retries: int = 3,
    tool_choice: str | dict = "auto",
) -> list[ToolCall]:
    """Call OpenRouter chat completions with tool-calling enabled.

    Returns the parsed tool calls the model made — an empty list if it made
    none, or if every returned tool call was malformed (unparseable
    arguments, missing name). Network/HTTP errors DO raise (httpx's own
    exceptions) — the caller decides what fallback behavior that implies;
    this function only absorbs "the model responded but the response
    doesn't make sense," not connectivity failures.

    Transient failures (HTTP 429 or 5xx) are retried up to `max_retries`
    attempts with exponential backoff, mirroring `synth/challenges.py`'s
    `call_openrouter`. Any other HTTP error or a connection error raises
    immediately — no retry.
    """
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set (env var, or pass api_key explicitly)")

    data: dict | None = None
    for attempt in range(max_retries):
        try:
            resp = httpx.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "tools": tools,
                    "tool_choice": tool_choice,
                    "temperature": 0.2,
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            break
        except httpx.HTTPStatusError as e:
            transient = e.response.status_code == 429 or e.response.status_code >= 500
            if not transient or attempt >= max_retries - 1:
                raise
            time.sleep(min(2**attempt, 10))
    assert data is not None  # loop always either breaks with data set or raises

    raw_calls = data["choices"][0]["message"].get("tool_calls") or []
    result: list[ToolCall] = []
    for call in raw_calls:
        fn = call.get("function", {})
        name = fn.get("name")
        if not name:
            continue
        try:
            arguments = json.loads(fn.get("arguments", "{}"))
        except json.JSONDecodeError:
            continue
        if not isinstance(arguments, dict):
            continue
        result.append(ToolCall(name=name, arguments=arguments))
    return result


def call_openrouter_tools_traced(
    model: str,
    system: str,
    user: str,
    tools: list[dict],
    api_key: str | None = None,
    timeout: float = 30.0,
    max_retries: int = 3,
    trace_name: str | None = None,
) -> list[ToolCall]:
    """call_openrouter_tools wrapped with Langfuse tracing and Prometheus metrics.

    Falls back to untraced call when Langfuse is unavailable — never blocks execution.
    """
    from webx5.utils.metrics import LLM_GENERATION_SUCCESS, LLM_GENERATION_FAILED

    user_id = user_id_context.get()
    llm_trace = start_llm_trace(
        trace_name or "openrouter_tool_call",
        model,
        {"system": system, "user": user, "tools": tools},
    )

    try:
        result = call_openrouter_tools(model, system, user, tools, api_key, timeout, max_retries)
        LLM_GENERATION_SUCCESS.labels(model=model).inc()
        llm_trace.end_success([{"name": tc.name, "arguments": tc.arguments} for tc in result])

        _log.info(
            "llm.call_completed",
            model=model,
            tool_calls_count=len(result),
            duration_ms=llm_trace.duration_ms,
            user_id=user_id,
        )
        return result

    except Exception as exc:
        error_type = type(exc).__name__
        LLM_GENERATION_FAILED.labels(model=model, error_type=error_type).inc()
        llm_trace.end_error(exc)
        _log.error("llm.call_failed", model=model, error_type=error_type, duration_ms=llm_trace.duration_ms)
        raise
