from __future__ import annotations

from unittest.mock import MagicMock

from webx5.core.langfuse_client import LLMTrace, start_llm_trace
from webx5.utils.contextvars_utils import user_id_context


def test_start_llm_trace_sets_input_on_trace_and_generation(monkeypatch) -> None:
    generation = MagicMock()
    trace = MagicMock()
    trace.generation.return_value = generation
    langfuse = MagicMock()
    langfuse.trace.return_value = trace
    monkeypatch.setattr("webx5.core.langfuse_client.get_langfuse", lambda: langfuse)

    token = user_id_context.set("user-1")
    try:
        input_data = [{"role": "user", "content": "hi"}]
        handle = start_llm_trace("challenge_generation", "test/model", input_data)
    finally:
        user_id_context.reset(token)

    langfuse.trace.assert_called_once()
    assert langfuse.trace.call_args.kwargs["name"] == "challenge_generation"
    assert langfuse.trace.call_args.kwargs["input"] == input_data
    assert langfuse.trace.call_args.kwargs["user_id"] == "user-1"
    trace.generation.assert_called_once()
    assert trace.generation.call_args.kwargs["input"] == input_data
    assert handle.trace is trace
    assert handle.generation is generation


def test_start_llm_trace_keeps_trace_when_generation_create_fails(monkeypatch) -> None:
    trace = MagicMock()
    trace.generation.side_effect = RuntimeError("payload too large")
    langfuse = MagicMock()
    langfuse.trace.return_value = trace
    monkeypatch.setattr("webx5.core.langfuse_client.get_langfuse", lambda: langfuse)

    handle = start_llm_trace("challenge_generation", "test/model", {"system": "s"})

    assert handle.trace is trace
    assert handle.generation is None
    handle.end_success("ok")
    trace.update.assert_called_once()
    assert trace.update.call_args.kwargs["output"] == "ok"
    langfuse.flush.assert_called_once()


def test_end_success_writes_output_on_trace_and_generation() -> None:
    langfuse = MagicMock()
    trace = MagicMock()
    generation = MagicMock()
    handle = LLMTrace(langfuse=langfuse, trace=trace, generation=generation)

    handle.end_success("model-output")

    generation.end.assert_called_once()
    assert generation.end.call_args.kwargs["output"] == "model-output"
    trace.update.assert_called_once()
    assert trace.update.call_args.kwargs["output"] == "model-output"
    langfuse.flush.assert_called_once()


def test_start_llm_trace_is_noop_when_langfuse_disabled(monkeypatch) -> None:
    monkeypatch.setattr("webx5.core.langfuse_client.get_langfuse", lambda: None)

    handle = start_llm_trace("challenge_generation", "test/model", {"system": "s"})

    handle.end_success("unused")
    assert handle.langfuse is None
    assert handle.trace is None
    assert handle.generation is None
