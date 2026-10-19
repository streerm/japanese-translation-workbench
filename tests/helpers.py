"""Shared helpers for tests that script a fake model."""

from __future__ import annotations

import re
from collections.abc import Callable

from jtw.llm.fake import FakeCall

_KEY_LINE = re.compile(r"^\[(S\d{3})\]\n(?=[^\n\[]*[぀-鿿])", re.MULTILINE)


def requested_keys(prompt: str) -> list[str]:
    """Keys whose marker line is followed by Japanese source text (skips format examples)."""
    return _KEY_LINE.findall(prompt + "\n")


def english(key: str, column: str = "x") -> str:
    return f"English {column} {key}."


def translator(column: str = "x", drop: tuple[str, ...] = ()) -> Callable[[FakeCall], str]:
    """A scripted step answering every requested key except ``drop``."""

    def step(call: FakeCall) -> str:
        keys = [k for k in requested_keys(call.prompt) if k not in drop]
        return "\n\n".join(f"[{k}]\n{english(k, column)}" for k in keys)

    return step
