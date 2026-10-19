"""Typographic clean-up for English output, and ``**bold**``/``*italic*`` markup parsing."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

_MARKUP_RE = re.compile(r"(\*\*\*[^*]+\*\*\*|\*\*[^*]+\*\*|\*[^*]+\*)")


@dataclass(frozen=True)
class Run:
    text: str
    bold: bool = False
    italic: bool = False


def smarten(text: str) -> str:
    """Ellipses and curly quotes: ``...`` -> ``…``, ``"x"`` -> ``“x”``, ``don't`` -> ``don’t``."""
    text = text.replace("...", "…")
    text = re.sub(r"(^|[\s(\[{—–-])\"", "\\1\u201c", text)
    text = text.replace('"', "\u201d")
    text = re.sub(r"(\w)'(\w)", "\\1\u2019\\2", text)
    text = re.sub(r"(^|[\s(\[{—–-])'", "\\1\u2018", text)
    return text.replace("'", "\u2019")


def runs(text: str) -> Iterator[Run]:
    """Split markdown-lite text into formatted runs."""
    for piece in _MARKUP_RE.split(text):
        if not piece:
            continue
        if piece.startswith("***") and piece.endswith("***") and len(piece) > 6:
            yield Run(piece[3:-3], bold=True, italic=True)
        elif piece.startswith("**") and piece.endswith("**") and len(piece) > 4:
            yield Run(piece[2:-2], bold=True)
        elif piece.startswith("*") and piece.endswith("*") and len(piece) > 2:
            yield Run(piece[1:-1], italic=True)
        else:
            yield Run(piece)
