"""A scripted provider for tests and offline demos. It never touches the network."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from jtw.llm.base import Message, ModelResult, Usage


@dataclass(frozen=True)
class FakeCall:
    kind: str  #: "complete" or "conversation"
    model: str
    system: str | None
    max_tokens: int
    messages: tuple[Message, ...]

    @property
    def prompt(self) -> str:
        """The last user message (the whole prompt, for ``complete`` calls)."""
        return self.messages[-1]["content"]


#: A scripted step: a reply, an error to raise, a full result, or a function of the call.
Step = str | Exception | ModelResult | Callable[[FakeCall], "str | ModelResult"]


@dataclass
class FakeProvider:
    """Replays ``script`` in order, one step per call, and records every call.

    ``served_model`` overrides the model reported back (to exercise the mismatch guard);
    by default the requested model is echoed.
    """

    script: list[Step] = field(default_factory=list)
    served_model: str | None = None
    name: str = "fake"
    calls: list[FakeCall] = field(default_factory=list)

    def complete(
        self, prompt: str, *, model: str, system: str | None = None, max_tokens: int
    ) -> ModelResult:
        message: Message = {"role": "user", "content": prompt}
        return self._run(FakeCall("complete", model, system, max_tokens, (message,)))

    def conversation(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        system: str | None = None,
        max_tokens: int,
    ) -> ModelResult:
        return self._run(FakeCall("conversation", model, system, max_tokens, tuple(messages)))

    def _run(self, call: FakeCall) -> ModelResult:
        self.calls.append(call)
        if not self.script:
            raise AssertionError(f"FakeProvider script exhausted at call {len(self.calls)}")
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        if callable(step):
            step = step(call)
        if isinstance(step, ModelResult):
            return step
        return ModelResult(
            text=step,
            model=self.served_model or call.model,
            usage=Usage(input_tokens=len(call.prompt), output_tokens=len(step)),
            stop_reason="end_turn",
        )
