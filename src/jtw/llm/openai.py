"""OpenAI Responses API adapter.

``temperature`` is never sent: reasoning models (the ``gpt-5``/``gpt-6`` families and the
o-series) only accept the default. For those models depth is set with ``reasoning.effort``.
An incomplete response (output budget exhausted) is reported as ``stop_reason`` =
``"incomplete:<reason>"`` so the caller can treat it as truncated.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from jtw.llm.base import Message, ModelRefusal, ModelResult, Usage, require_key

ENV_VAR = "OPENAI_API_KEY"
REASONING_MODEL_PREFIXES = ("gpt-5", "gpt-6", "o1", "o3", "o4")


def is_reasoning_model(model: str) -> bool:
    return model.startswith(REASONING_MODEL_PREFIXES)


def _default_client(api_key: str, timeout: float) -> Any:
    import openai

    return openai.OpenAI(api_key=api_key, timeout=timeout)


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        *,
        timeout_s: float,
        reasoning_effort: str = "medium",
        client_factory: Callable[[str, float], Any] = _default_client,
    ) -> None:
        self._timeout = timeout_s
        self._effort = reasoning_effort
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
        return self._create(prompt, model=model, system=system, max_tokens=max_tokens)

    def conversation(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        system: str | None = None,
        max_tokens: int,
    ) -> ModelResult:
        return self._create(
            [dict(m) for m in messages], model=model, system=system, max_tokens=max_tokens
        )

    def _create(
        self, payload: object, *, model: str, system: str | None, max_tokens: int
    ) -> ModelResult:
        kwargs: dict[str, Any] = {
            "model": model,
            "input": payload,
            "max_output_tokens": max_tokens,
        }
        if system:
            kwargs["instructions"] = system
        if is_reasoning_model(model):
            kwargs["reasoning"] = {"effort": self._effort}
        return _to_result(self.client.responses.create(**kwargs), model)


def _to_result(response: Any, requested: str) -> ModelResult:
    status = str(response.status or "")
    if status == "incomplete":
        details = response.incomplete_details
        reason = str(getattr(details, "reason", None) or "unknown")
        if reason == "content_filter":
            raise ModelRefusal(f"{requested} declined the request (content filter)")
        status = f"incomplete:{reason}"
    usage = response.usage
    return ModelResult(
        text=str(response.output_text or "").strip(),
        model=str(response.model),
        usage=Usage(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        ),
        stop_reason=status,
    )
