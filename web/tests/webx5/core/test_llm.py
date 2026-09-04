from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from webx5.core.llm import ToolCall, call_openrouter_tools


def _fake_response(tool_calls: list[dict] | None) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"choices": [{"message": {"tool_calls": tool_calls}}]}
    return resp


def test_call_openrouter_tools_parses_valid_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_calls = [
        {"function": {"name": "add_item", "arguments": json.dumps({"sku_id": "sku_1", "quantity": 2})}},
    ]
    monkeypatch.setattr("webx5.core.llm.httpx.post", lambda *a, **k: _fake_response(fake_calls))

    result = call_openrouter_tools(model="fake/model", system="s", user="u", tools=[], api_key="k")

    assert len(result) == 1
    assert result[0].name == "add_item"
    assert result[0].arguments == {"sku_id": "sku_1", "quantity": 2}


def test_call_openrouter_tools_returns_empty_list_when_no_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("webx5.core.llm.httpx.post", lambda *a, **k: _fake_response(None))

    result = call_openrouter_tools(model="fake/model", system="s", user="u", tools=[], api_key="k")

    assert result == []


def test_call_openrouter_tools_skips_malformed_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_calls = [{"function": {"name": "add_item", "arguments": "not json"}}]
    monkeypatch.setattr("webx5.core.llm.httpx.post", lambda *a, **k: _fake_response(fake_calls))

    result = call_openrouter_tools(model="fake/model", system="s", user="u", tools=[], api_key="k")

    assert result == []


def test_call_openrouter_tools_skips_calls_missing_a_name(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_calls = [{"function": {"arguments": "{}"}}]
    monkeypatch.setattr("webx5.core.llm.httpx.post", lambda *a, **k: _fake_response(fake_calls))

    result = call_openrouter_tools(model="fake/model", system="s", user="u", tools=[], api_key="k")

    assert result == []


def test_call_openrouter_tools_raises_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        call_openrouter_tools(model="fake/model", system="s", user="u", tools=[], api_key=None)
