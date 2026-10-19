"""Anthropic Messages API adapter.

Requests never include ``temperature`` (current Claude models reject it) or a ``thinking``
block (omitting it leaves the model's default, adaptive thinking in place). Calls stream and
collect the final message, because a part-sized generation can outlast a non-streaming HTTP
timeout.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from jtw.llm.base import Message, ModelRefusal, ModelResult, Usage, require_key

ENV_VAR = "ANTHROPIC_API_KEY"


def _default_client(api_key: str, timeout: float) -> Any:
    import anthropic

    return anthropic.Anthropic(api_key=api_key, timeout=timeout)


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        *,
        timeout_s: float,
        client_factory: Callable[[str, float], Any] = _default_client,
    ) -> None:
        self._timeout = timeout_s
        self._factory = client_factory
        self._client: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._factory(require_key(ENV_VAR), self._timeout)
        return self._client

    def complete(
        self, prompt: str, *, model: str, system: str | None = None, max_tokens: int
    ) -> ModelResult:
        return self.conversation(
            [{"role": "user", "content": prompt}],
            model=model,
            system=system,
            max_tokens=max_tokens,
        )

    def conversation(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        system: str | None = None,
        max_tokens: int,
    ) -> ModelResult:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [dict(m) for m in messages],
        }
        if system:
            kwargs["system"] = system
        with self.client.messages.stream(**kwargs) as stream:
            message = stream.get_final_message()
        return _to_result(message, model)


def _to_result(message: Any, requested: str) -> ModelResult:
    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        category = getattr(details, "category", None)
        raise ModelRefusal(
            f"{requested} declined the request" + (f" (category: {category})" if category else "")
        )
    text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    )
    usage = message.usage
    return ModelResult(
        text=text.strip(),
        model=str(message.model),
        usage=Usage(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        ),
        stop_reason=str(message.stop_reason or ""),
    )
