from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from jtw.llm.anthropic import AnthropicProvider
from jtw.llm.base import MissingAPIKey, ModelRefusal
from jtw.llm.openai import OpenAIProvider, is_reasoning_model


class _Stream:
    def __init__(self, message: Any) -> None:
        self.message = message

    def __enter__(self) -> _Stream:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get_final_message(self) -> Any:
        return self.message


class FakeAnthropicClient:
    def __init__(self, message: Any) -> None:
        self.kwargs: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(stream=self._stream)
        self._message = message

    def _stream(self, **kwargs: Any) -> _Stream:
        self.kwargs.append(kwargs)
        return _Stream(self._message)


def _anthropic_message(stop_reason: str = "end_turn", **extra: Any) -> Any:
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="hmm"),
            SimpleNamespace(type="text", text="  [S001]\nHello. "),
        ],
        model="claude-test-1-20260101",
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        stop_reason=stop_reason,
        **extra,
    )


def _anthropic(message: Any) -> tuple[AnthropicProvider, FakeAnthropicClient, list[Any]]:
    client = FakeAnthropicClient(message)
    seen: list[Any] = []

    def factory(key: str, timeout: float) -> FakeAnthropicClient:
        seen.append((key, timeout))
        return client

    return AnthropicProvider(timeout_s=99, client_factory=factory), client, seen


@pytest.fixture(autouse=True)
def _keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")


def test_anthropic_request_shape() -> None:
    provider, client, seen = _anthropic(_anthropic_message())
    result = provider.complete("translate this", model="claude-test-1", system="sys", max_tokens=5)
    assert client.kwargs == [
        {
            "model": "claude-test-1",
            "max_tokens": 5,
            "messages": [{"role": "user", "content": "translate this"}],
            "system": "sys",
        }
    ]
    assert "temperature" not in client.kwargs[0] and "thinking" not in client.kwargs[0]
    assert seen == [("test-anthropic", 99)]
    assert result.text == "[S001]\nHello."
    assert result.model == "claude-test-1-20260101"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (11, 7)
    assert not result.truncated


def test_anthropic_client_is_lazy_and_reused() -> None:
    provider, client, seen = _anthropic(_anthropic_message())
    assert seen == []
    provider.complete("a", model="m", max_tokens=1)
    provider.conversation(
        [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}],
        model="m",
        max_tokens=1,
    )
    assert len(seen) == 1
    assert "system" not in client.kwargs[1]
    assert [m["role"] for m in client.kwargs[1]["messages"]] == ["user", "assistant"]


def test_anthropic_refusal_and_truncation() -> None:
    details = SimpleNamespace(category="policy")
    provider, _, _ = _anthropic(_anthropic_message("refusal", stop_details=details))
    with pytest.raises(ModelRefusal, match="policy"):
        provider.complete("x", model="m", max_tokens=1)
    provider, _, _ = _anthropic(_anthropic_message("max_tokens"))
    assert provider.complete("x", model="m", max_tokens=1).truncated


def test_missing_key_names_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    provider, _, _ = _anthropic(_anthropic_message())
    with pytest.raises(MissingAPIKey, match="ANTHROPIC_API_KEY") as info:
        provider.complete("x", model="m", max_tokens=1)
    assert info.value.env_var == "ANTHROPIC_API_KEY"

    monkeypatch.setenv("OPENAI_API_KEY", "  ")
    with pytest.raises(MissingAPIKey, match="OPENAI_API_KEY"):
        OpenAIProvider(timeout_s=1, client_factory=lambda k, t: None).complete(
            "x", model="m", max_tokens=1
        )


class FakeOpenAIClient:
    def __init__(self, response: Any) -> None:
        self.kwargs: list[dict[str, Any]] = []
        self.responses = SimpleNamespace(create=self._create)
        self._response = response

    def _create(self, **kwargs: Any) -> Any:
        self.kwargs.append(kwargs)
        return self._response


def _openai_response(status: str = "completed", reason: str | None = None) -> Any:
    return SimpleNamespace(
        status=status,
        incomplete_details=SimpleNamespace(reason=reason) if reason else None,
        output_text=" Hello. ",
        model="gpt-6-test-2026-01-01",
        usage=SimpleNamespace(input_tokens=3, output_tokens=4),
    )


def _openai(response: Any, **kw: Any) -> tuple[OpenAIProvider, FakeOpenAIClient]:
    client = FakeOpenAIClient(response)
    return OpenAIProvider(timeout_s=5, client_factory=lambda k, t: client, **kw), client


def test_openai_reasoning_model_request_shape() -> None:
    provider, client = _openai(_openai_response(), reasoning_effort="high")
    result = provider.complete("p", model="gpt-6-test", system="sys", max_tokens=9)
    assert client.kwargs == [
        {
            "model": "gpt-6-test",
            "input": "p",
            "max_output_tokens": 9,
            "instructions": "sys",
            "reasoning": {"effort": "high"},
        }
    ]
    assert "temperature" not in client.kwargs[0]
    assert result.text == "Hello."
    assert result.stop_reason == "completed"
    assert result.usage.output_tokens == 4


def test_openai_non_reasoning_model_has_no_reasoning_block() -> None:
    provider, client = _openai(_openai_response())
    provider.conversation([{"role": "user", "content": "hi"}], model="chat-test", max_tokens=1)
    assert client.kwargs[0] == {
        "model": "chat-test",
        "input": [{"role": "user", "content": "hi"}],
        "max_output_tokens": 1,
    }
    assert is_reasoning_model("o3-mini") and not is_reasoning_model("chat-test")


def test_openai_incomplete_and_filtered() -> None:
    provider, _ = _openai(_openai_response("incomplete", "max_output_tokens"))
    result = provider.complete("p", model="m", max_tokens=1)
    assert result.stop_reason == "incomplete:max_output_tokens" and result.truncated
    provider, _ = _openai(_openai_response("incomplete", "content_filter"))
    with pytest.raises(ModelRefusal):
        provider.complete("p", model="m", max_tokens=1)
