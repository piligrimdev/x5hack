from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import httpx

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
) -> list[ToolCall]:
    """Call OpenRouter chat completions with tool-calling enabled.

    Returns the parsed tool calls the model made — an empty list if it made
    none, or if every returned tool call was malformed (unparseable
    arguments, missing name). Network/HTTP errors DO raise (httpx's own
    exceptions) — the caller decides what fallback behavior that implies;
    this function only absorbs "the model responded but the response
    doesn't make sense," not connectivity failures.
    """
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set (env var, or pass api_key explicitly)")

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
            "tool_choice": "auto",
            "temperature": 0.2,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()

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
        result.append(ToolCall(name=name, arguments=arguments))
    return result
