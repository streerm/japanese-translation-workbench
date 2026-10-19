"""The provider protocol and the result and error types every provider shares."""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict


class Message(TypedDict):
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class ModelResult:
    """A response plus the provenance needed to audit a bulk run."""

    text: str
    model: str  #: the model that actually served the response, as the provider reports it
    usage: Usage = Usage()
    stop_reason: str = ""

    @property
    def truncated(self) -> bool:
        """The model stopped because it ran out of output tokens."""
        return self.stop_reason == "max_tokens" or self.stop_reason.startswith("incomplete")


class LLMError(RuntimeError):
    """Base class for provider errors the pipeline knows how to report."""


class ModelRefusal(LLMError):
    """The model declined the request outright."""


class MissingAPIKey(LLMError):
    """The API key for a provider is not set."""

    def __init__(self, env_var: str) -> None:
        super().__init__(f"{env_var} is not set; add it to your environment or .env file")
        self.env_var = env_var


class ModelMismatch(LLMError):
    """The provider answered with a different model than the one requested."""

    def __init__(self, requested: str, returned: str) -> None:
        super().__init__(f"requested model {requested!r} but the response came from {returned!r}")
        self.requested = requested
        self.returned = returned


class Provider(Protocol):
    """What the pipeline and synthesisers need from a model provider."""

    name: str

    def complete(
        self, prompt: str, *, model: str, system: str | None = None, max_tokens: int
    ) -> ModelResult: ...

    def conversation(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        system: str | None = None,
        max_tokens: int,
    ) -> ModelResult: ...


def require_key(env_var: str) -> str:
    key = os.environ.get(env_var, "").strip()
    if not key:
        raise MissingAPIKey(env_var)
    return key
