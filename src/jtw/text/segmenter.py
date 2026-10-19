"""Plain text -> paragraphs -> segments -> parts.

Rules (see ``docs/data-model.md``):

* A blank line separates paragraphs; the lines of one paragraph are joined without spaces.
  A file with no blank lines at all is read as one paragraph per line.
* A paragraph is split into sentences after ``。！？`` (and ``!?``), keeping any closing
  brackets ``」』）`` with the sentence they close. Nothing inside brackets is split.
* A line of dialogue ``「…」`` is a segment of its own when nothing follows the closing
  bracket but another line of dialogue or the end of the paragraph; ``「…」と言った。``
  stays one segment.
* Parts are cut at the paragraph boundary nearest the character budget. With
  ``split_on_headings`` a heading line also starts a new chapter (and the heading becomes the
  chapter title rather than a segment).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from jtw.model.part import Part, SourceSegment, Structure
from jtw.model.segment import segment_key
from jtw.text.ja import (
    BRACKET_PAIRS,
    CLOSING_BRACKETS,
    DIALOGUE_CLOSE,
    DIALOGUE_OPEN,
    SENTENCE_END,
    char_count,
    is_heading,
    join_lines,
)

DEFAULT_PART_CHARS = 2500
_BLANK_LINE_RE = re.compile(r"\n[ \t　]*\n")


@dataclass(frozen=True)
class Paragraph:
    text: str
    heading: bool = False


def paragraphs(text: str, *, detect_headings: bool = False) -> list[Paragraph]:
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    if _BLANK_LINE_RE.search(text):
        chunks = [chunk.split("\n") for chunk in _BLANK_LINE_RE.split(text)]
    else:
        chunks = [[line] for line in text.split("\n")]
    result: list[Paragraph] = []
    for lines in chunks:
        lines = [line for line in lines if line.strip()]
        if not lines:
            continue
        if detect_headings and is_heading(lines[0]):
            result.append(Paragraph(lines[0].strip(), heading=True))
            lines = lines[1:]
            if not lines:
                continue
        result.append(Paragraph(join_lines(lines)))
    return result


def sentences(paragraph: str) -> list[str]:
    """Split one paragraph into segments."""
    out: list[str] = []
    stack: list[str] = []
    start = 0
    i = 0
    n = len(paragraph)
    while i < n:
        ch = paragraph[i]
        if ch in BRACKET_PAIRS:
            stack.append(BRACKET_PAIRS[ch])
        elif stack and ch == stack[-1]:
            stack.pop()
            if not stack and ch in DIALOGUE_CLOSE and paragraph[start] in DIALOGUE_OPEN:
                rest = paragraph[i + 1 :].lstrip()
                if not rest or rest[0] in DIALOGUE_OPEN:
                    out.append(paragraph[start : i + 1])
                    start = i + 1
        elif not stack and ch in SENTENCE_END:
            end = i + 1
            while end < n and paragraph[end] in SENTENCE_END + CLOSING_BRACKETS:
                end += 1
            out.append(paragraph[start:end])
            start = i = end
            continue
        i += 1
    out.append(paragraph[start:])
    return [s.strip() for s in out if s.strip()]


def _cut_parts(paras: list[str], budget: int) -> list[list[str]]:
    """Group paragraphs into parts, cutting at the boundary nearest ``budget`` characters."""
    parts: list[list[str]] = []
    current: list[str] = []
    count = 0
    for para in paras:
        size = char_count(para)
        if current and count + size > budget:
            if (count + size - budget) > (budget - count):
                parts.append(current)
                current, count = [], 0
            else:
                current.append(para)
                parts.append(current)
                current, count = [], 0
                continue
        current.append(para)
        count += size
    if current:
        parts.append(current)
    return parts


def _make_part(
    part_id: str, label: str, paras: list[str], chapter: str | None, chapter_title: str | None
) -> Part:
    texts = [s for para in paras for s in sentences(para)]
    segments = tuple(SourceSegment(segment_key(i), t) for i, t in enumerate(texts, start=1))
    return Part(part_id, label, segments, chapter, chapter_title)


def build_structure(
    text: str,
    *,
    part_chars: int = DEFAULT_PART_CHARS,
    split_on_headings: bool = False,
) -> Structure:
    if part_chars < 1:
        raise ValueError("part_chars must be positive")
    paras = paragraphs(text, detect_headings=split_on_headings)
    if not split_on_headings:
        groups = _cut_parts([p.text for p in paras], part_chars)
        width = max(2, len(str(len(groups))))
        return Structure(
            tuple(
                _make_part(f"P{i:0{width}d}", f"Part {i}", group, None, None)
                for i, group in enumerate(groups, start=1)
            )
        )

    chapters: list[tuple[str | None, list[str]]] = [(None, [])]
    for para in paras:
        if para.heading:
            chapters.append((para.text, []))
        else:
            chapters[-1][1].append(para.text)
    if not chapters[0][1]:
        chapters.pop(0)
        offset = 1
    else:
        offset = 0  # text before the first heading becomes chapter 0
    parts: list[Part] = []
    for c_index, (title, body) in enumerate(chapters, start=offset):
        for p_index, group in enumerate(_cut_parts(body, part_chars), start=1):
            label = f"Chapter {c_index} · Part {p_index}"
            parts.append(
                _make_part(f"C{c_index:02d}P{p_index:02d}", label, group, str(c_index), title)
            )
    if not parts:
        raise ValueError("the text contains no segments")
    return Structure(tuple(parts))
