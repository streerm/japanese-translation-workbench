"""Bilingual search across every part of a project.

Japanese queries match the source; English queries match the final text and every MT column
(case-insensitively). Each hit carries its neighbouring segments for context.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

from jtw.config import Project
from jtw.model import store
from jtw.model.part import qualified_ref
from jtw.model.segment import Segment
from jtw.text.ja import looks_untranslated

Lang = Literal["ja", "en", "both"]


@dataclass(frozen=True)
class Hit:
    part_id: str
    part_label: str
    segment: Segment
    fields: list[str]  #: "source", "final", "notes" or an MT column id
    before: list[Segment] = field(default_factory=list)
    after: list[Segment] = field(default_factory=list)

    @property
    def ref(self) -> str:
        return qualified_ref(self.part_id, self.segment.key)


def guess_lang(query: str) -> Lang:
    return "ja" if looks_untranslated(query) else "en"


def _matching_fields(segment: Segment, needle: str, lang: Lang) -> list[str]:
    fields: list[str] = []
    if lang in ("ja", "both") and needle in segment.source.lower():
        fields.append("source")
    if lang in ("en", "both"):
        if needle in segment.final.lower():
            fields.append("final")
        fields.extend(c for c, text in segment.mt.items() if needle in text.lower())
        if needle in segment.notes.lower():
            fields.append("notes")
    return fields


def search(
    project: Project, query: str, *, lang: Lang | None = None, context: int = 1
) -> list[Hit]:
    needle = query.strip().lower()
    if not needle:
        return []
    lang = lang or "both"
    structure = store.load_source(project.paths)
    hits: list[Hit] = []
    for part in structure.parts:
        loaded = store.load_part(project.paths, part.id, project.config.columns, structure)
        segments = list(loaded.segments.values())
        for i, segment in enumerate(segments):
            fields = _matching_fields(segment, needle, lang)
            if fields:
                hits.append(
                    Hit(
                        part.id,
                        part.label,
                        segment,
                        fields,
                        segments[max(0, i - context) : i],
                        segments[i + 1 : i + 1 + context],
                    )
                )
    return hits


def highlight_spans(text: str, query: str) -> Iterator[tuple[str, bool]]:
    """Split ``text`` into ``(piece, is_match)`` pairs, matching case-insensitively."""
    if not query:
        yield text, False
        return
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    position = 0
    for match in pattern.finditer(text):
        if match.start() > position:
            yield text[position : match.start()], False
        yield match.group(0), True
        position = match.end()
    if position < len(text):
        yield text[position:], False


def highlight(text: str, query: str, start: str = "**", end: str = "**") -> str:
    return "".join(f"{start}{p}{end}" if hit else p for p, hit in highlight_spans(text, query))
