from __future__ import annotations

from unittest.mock import MagicMock

import synth.challenges as synth_challenges

from webx5.services import openrouter_capturing as capturing


def _reset_patch_state(monkeypatch) -> None:
    monkeypatch.setattr(capturing, "_patch_depth", 0)
    monkeypatch.setattr(capturing, "_original_call_openrouter", None)


def test_capture_openrouter_io_traces_prompt_and_response(monkeypatch) -> None:
    _reset_patch_state(monkeypatch)
    original = MagicMock(return_value='{"challenge_title": "ok"}')
    monkeypatch.setattr(synth_challenges, "call_openrouter", original)
    trace = MagicMock()
    start = MagicMock(return_value=trace)
    monkeypatch.setattr(capturing, "start_llm_trace", start)
    monkeypatch.setattr(capturing.LLM_GENERATION_SUCCESS, "labels", lambda **_: MagicMock())

    with capturing.capture_openrouter_io() as captured:
        result = synth_challenges.call_openrouter(
            "test/model", "sys prompt", "user prompt", api_key="k"
        )

    assert result == '{"challenge_title": "ok"}'
    assert captured["system"] == "sys prompt"
    assert captured["user"] == "user prompt"
    assert captured["response"] == '{"challenge_title": "ok"}'
    start.assert_called_once()
    assert start.call_args.args[0] == "challenge_generation"
    assert start.call_args.args[1] == "test/model"
    assert start.call_args.args[2] == [
        {"role": "system", "content": "sys prompt"},
        {"role": "user", "content": "user prompt"},
    ]
    assert start.call_args.kwargs["generation_name"] == "challenge_generation"
    trace.end_success.assert_called_once_with('{"challenge_title": "ok"}')
    original.assert_called_once()
    assert synth_challenges.call_openrouter is original


def test_capture_openrouter_io_records_error_and_restores(monkeypatch) -> None:
    _reset_patch_state(monkeypatch)
    original = MagicMock(side_effect=RuntimeError("offline"))
    monkeypatch.setattr(synth_challenges, "call_openrouter", original)
    trace = MagicMock()
    monkeypatch.setattr(capturing, "start_llm_trace", MagicMock(return_value=trace))
    monkeypatch.setattr(capturing.LLM_GENERATION_FAILED, "labels", lambda **_: MagicMock())

    try:
        with capturing.capture_openrouter_io() as captured:
            synth_challenges.call_openrouter("m", "s", "u")
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")

    assert captured["error"] == "offline"
    trace.end_error.assert_called_once()
    assert synth_challenges.call_openrouter is original
