"""The segment-key protocol: how a part is sent to a model and how the reply is checked.

Each segment is sent under a marker line such as ``[S012]`` and the model must answer with the
same markers, one block per key, in order. The parser is *lenient about presentation* (bold
markers, a trailing colon, text on the marker line, code fences, a chatty preamble or
sign-off, CRLF line endings) and *strict about substance*: a key is accepted only if it comes
back exactly once, was asked for, is not fused with a neighbour, and holds non-empty English.
Everything else is reported, by category, so the caller can keep the good blocks and ask
again for the rest.

See ``docs/mt-protocol.md`` for worked examples.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from jtw.model.segment import key_index
from jtw.text.ja import looks_untranslated


def marker(key: str) -> str:
    """``"S012"`` -> ``"[S012]"``."""
    return f"[{key}]"


def render_segments(segments: Mapping[str, str]) -> str:
    """Marker-delimited source text, ready for the ``{segments}`` prompt slot."""
    return "\n\n".join(f"{marker(key)}\n{text}" for key, text in segments.items())


# A marker at the start of a line, optionally wrapped in bold/italic or preceded by a heading
# or list mark, optionally followed by a colon. Anything looser starts matching prose.
_DECOR = r"(?:\*\*|__|\*|_)?"
_MARKER_RE = re.compile(
    rf"^[ \t]*(?:#{{1,6}}[ \t]+|[-*][ \t]+)?{_DECOR}\[[ \t]*[Ss][ \t]*(\d{{1,4}})[ \t]*\]"
    rf"{_DECOR}[ \t]*:?{_DECOR}[ \t]*",
    re.MULTILINE,
)
# Two or more keys fused into one marker: [S003-S004], [S003–4], [S003, S004], [S003/S004].
_COMBINED_RE = re.compile(
    rf"^[ \t]*{_DECOR}\[[ \t]*[Ss](\d{{1,4}})[ \t]*(?:[-–—,/&+]|and)[ \t]*[Ss]?(\d{{1,4}})"
    rf"[ \t]*\]{_DECOR}[ \t]*:?{_DECOR}[ \t]*",
    re.MULTILINE,
)
_FENCE_LINE_RE = re.compile(r"^[ \t]*```[^\n]*$\n?", re.MULTILINE)
_RULE_RE = re.compile(r"^[ \t]*(?:-{3,}|\*{3,}|_{3,})[ \t]*$", re.MULTILINE)
_PARAGRAPH_BREAK_RE = re.compile(r"\n[ \t]*\n")


class Problem(StrEnum):
    MISSING = "missing"
    EMPTY = "empty"
    DUPLICATE = "duplicate"
    INVENTED = "invented"
    MERGED = "merged"
    UNTRANSLATED = "untranslated"


_DESCRIPTIONS = {
    Problem.DUPLICATE: "returned more than once",
    Problem.INVENTED: "not requested",
    Problem.MERGED: "merged with a neighbouring segment",
    Problem.EMPTY: "returned with no translation",
    Problem.UNTRANSLATED: "returned still in Japanese",
    Problem.MISSING: "not returned at all",
}


@dataclass
class ParseProblems:
    """Rejected keys by category. ``invented`` keys were never requested."""

    by_kind: dict[Problem, list[str]] = field(default_factory=dict)
    no_markers: bool = False

    def add(self, kind: Problem, key: str) -> None:
        keys = self.by_kind.setdefault(kind, [])
        if key not in keys:
            keys.append(key)

    def keys(self, kind: Problem) -> list[str]:
        return list(self.by_kind.get(kind, []))

    def __bool__(self) -> bool:
        return self.no_markers or any(self.by_kind.values())

    def describe(self) -> str:
        """One line per category, e.g. ``"keys not returned at all: S004, S005"``."""
        lines = []
        if self.no_markers:
            lines.append("the response contained no [Snnn] segment keys")
        for kind in _DESCRIPTIONS:
            keys = self.by_kind.get(kind)
            if keys:
                ordered = sorted(keys, key=key_index)
                lines.append(f"keys {_DESCRIPTIONS[kind]}: {', '.join(ordered)}")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, list[str]]:
        return {kind.value: sorted(keys, key=key_index) for kind, keys in self.by_kind.items()}


@dataclass
class ParseResult:
    translations: dict[str, str]
    problems: ParseProblems

    @property
    def ok(self) -> bool:
        return not self.problems


def _key(number: int) -> str:
    # Not segment_key(): a reply may contain an out-of-range key such as [S000], which must be
    # reported as invented rather than rejected outright.
    return f"S{number:03d}"


@dataclass(frozen=True)
class _Block:
    keys: tuple[str, ...]
    body: str


def _split_blocks(text: str) -> list[_Block]:
    """Cut a response into blocks at every (single or combined) marker."""
    hits: list[tuple[int, int, tuple[str, ...]]] = []
    for match in _COMBINED_RE.finditer(text):
        first, last = int(match.group(1)), int(match.group(2))
        span = range(first, last + 1) if last > first else (first, last)
        hits.append((match.start(), match.end(), tuple(_key(i) for i in span)))
    combined_starts = {start for start, _, _ in hits}
    for match in _MARKER_RE.finditer(text):
        if match.start() not in combined_starts:
            hits.append((match.start(), match.end(), (_key(int(match.group(1))),)))
    hits.sort()
    blocks = []
    for i, (_, body_start, keys) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        blocks.append(_Block(keys, text[body_start:end]))
    return blocks


def _clean(body: str, *, last: bool) -> str:
    """Normalise a block body. The final block also loses any sign-off after it."""
    if last:
        body = _RULE_RE.split(body, maxsplit=1)[0]
        body = _PARAGRAPH_BREAK_RE.split(body.strip(), maxsplit=1)[0]
    lines = [line.strip() for line in body.strip().splitlines()]
    return "\n".join(line for line in lines if line)


def parse_response(text: str, keys: Sequence[str]) -> ParseResult:
    """Map a model's reply back onto the requested ``keys``. Never raises.

    Returns the accepted ``{key: translation}`` plus every rejected key by category.
    """
    # A fence line becomes a paragraph break, so a sign-off after a closing fence is cut off.
    text = _FENCE_LINE_RE.sub("\n", (text or "").replace("\r\n", "\n").replace("\r", "\n"))
    problems = ParseProblems()
    blocks = _split_blocks(text)
    if not blocks:
        problems.no_markers = True
        for key in keys:
            problems.add(Problem.MISSING, key)
        return ParseResult({}, problems)

    wanted = set(keys)
    seen: dict[str, int] = {}
    bodies: dict[str, str] = {}
    for i, block in enumerate(blocks):
        body = _clean(block.body, last=i == len(blocks) - 1)
        if len(block.keys) > 1:
            for key in block.keys:
                problems.add(Problem.MERGED if key in wanted else Problem.INVENTED, key)
            continue
        key = block.keys[0]
        seen[key] = seen.get(key, 0) + 1
        bodies.setdefault(key, body)

    for key, count in seen.items():
        if key not in wanted:
            problems.add(Problem.INVENTED, key)
        elif count > 1:
            problems.add(Problem.DUPLICATE, key)

    translations: dict[str, str] = {}
    for key in keys:
        if key in problems.keys(Problem.MERGED) or key in problems.keys(Problem.DUPLICATE):
            continue
        if key not in seen:
            continue
        body = bodies[key]
        if not body:
            problems.add(Problem.EMPTY, key)
        elif looks_untranslated(body):
            problems.add(Problem.UNTRANSLATED, key)
        else:
            translations[key] = body

    _classify_absent(keys, seen, problems)
    return ParseResult(translations, problems)


def _classify_absent(keys: Sequence[str], seen: Mapping[str, int], problems: ParseProblems) -> None:
    """Keys never returned: *merged* if they fall in a gap between returned keys (the model
    folded them into a neighbour), *missing* if they trail off the end (typically truncation).
    """
    flagged = set(problems.keys(Problem.MERGED))
    returned_positions = [i for i, key in enumerate(keys) if key in seen or key in flagged]
    last_returned = max(returned_positions, default=-1)
    for i, key in enumerate(keys):
        if key in seen or key in flagged:
            continue
        problems.add(Problem.MERGED if i < last_returned else Problem.MISSING, key)
