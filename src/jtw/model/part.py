"""Parts and chapters: how a work is divided for translation and navigation.

A *part* is the unit of one MT request: a continuous passage, short enough for a model to
translate in one go while holding a single voice. Parts can be grouped into chapters for
the sidebar.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

PART_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def qualified_ref(part_id: str, key: str) -> str:
    """``("C01P01", "S001")`` -> ``"C01P01/S001"``."""
    return f"{part_id}/{key}"


@dataclass(frozen=True)
class SourceSegment:
    key: str
    source: str


@dataclass(frozen=True)
class Part:
    id: str
    label: str
    segments: tuple[SourceSegment, ...]
    chapter: str | None = None
    chapter_title: str | None = None

    @property
    def keys(self) -> list[str]:
        return [s.key for s in self.segments]

    def source_text(self, key: str) -> str:
        for segment in self.segments:
            if segment.key == key:
                return segment.source
        raise KeyError(key)


@dataclass(frozen=True)
class Chapter:
    id: str
    title: str | None
    parts: tuple[Part, ...]

    @property
    def label(self) -> str:
        return f"Chapter {self.id}" + (f" · {self.title}" if self.title else "")


@dataclass(frozen=True)
class Structure:
    """The ordered parts of a work."""

    parts: tuple[Part, ...]

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for part in self.parts:
            if part.id in seen:
                raise ValueError(f"duplicate part id {part.id!r}")
            seen.add(part.id)

    @property
    def ids(self) -> list[str]:
        return [p.id for p in self.parts]

    def part_by_id(self, part_id: str) -> Part:
        for part in self.parts:
            if part.id == part_id:
                return part
        raise KeyError(f"no part {part_id!r}")

    def label(self, part_id: str) -> str:
        return self.part_by_id(part_id).label

    def chapters(self) -> list[Chapter]:
        """Consecutive parts sharing a chapter key, in order. Ungrouped parts get their own."""
        groups: list[tuple[str | None, list[Part]]] = []
        for part in self.parts:
            if groups and part.chapter is not None and groups[-1][0] == part.chapter:
                groups[-1][1].append(part)
            else:
                groups.append((part.chapter, [part]))
        return [
            Chapter(
                id=chapter if chapter is not None else parts[0].id,
                title=parts[0].chapter_title,
                parts=tuple(parts),
            )
            for chapter, parts in groups
        ]

    def select(self, specs: Iterable[str]) -> list[Part]:
        """Resolve part selectors (ids, 1-based positions or ``a-b`` ranges of positions).

        The result keeps document order and has no duplicates.
        """
        wanted: set[str] = set()
        for raw in specs:
            spec = raw.strip()
            if not spec:
                continue
            wanted.update(self._resolve(spec))
        return [p for p in self.parts if p.id in wanted]

    def _resolve(self, spec: str) -> Sequence[str]:
        if spec in self.ids:
            return [spec]
        range_match = re.fullmatch(r"(\d+)-(\d+)", spec)
        if range_match:
            first, last = int(range_match.group(1)), int(range_match.group(2))
            if first > last:
                raise ValueError(f"empty part range {spec!r}")
            return [self._by_position(i) for i in range(first, last + 1)]
        if spec.isdigit():
            return [self._by_position(int(spec))]
        raise ValueError(f"no part {spec!r}")

    def _by_position(self, position: int) -> str:
        if not 1 <= position <= len(self.parts):
            raise ValueError(f"part position {position} out of range 1-{len(self.parts)}")
        return self.parts[position - 1].id
