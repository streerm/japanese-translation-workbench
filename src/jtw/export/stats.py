"""Progress statistics: Japanese character counts and how much is translated and finalised."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from jtw.config import Project
from jtw.model import store
from jtw.model.store import LoadedPart
from jtw.text.ja import char_count


@dataclass(frozen=True)
class PartStats:
    part_id: str
    label: str
    chapter: str | None
    segments: int
    chars: int
    finalized_segments: int
    finalized_chars: int
    translated: dict[str, int]  #: per MT column: segments with text
    orphans: list[str] = field(default_factory=list)

    @property
    def finalized_pct(self) -> float:
        return 100.0 * self.finalized_chars / self.chars if self.chars else 0.0


@dataclass(frozen=True)
class ProjectStats:
    slug: str
    title: str
    columns: list[str]
    parts: list[PartStats]

    @property
    def chars(self) -> int:
        return sum(p.chars for p in self.parts)

    @property
    def segments(self) -> int:
        return sum(p.segments for p in self.parts)

    @property
    def finalized_chars(self) -> int:
        return sum(p.finalized_chars for p in self.parts)

    @property
    def finalized_pct(self) -> float:
        return 100.0 * self.finalized_chars / self.chars if self.chars else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "title": self.title,
            "columns": self.columns,
            "totals": {
                "segments": self.segments,
                "chars": self.chars,
                "finalized_chars": self.finalized_chars,
                "finalized_pct": round(self.finalized_pct, 1),
            },
            "parts": [
                {**asdict(p), "finalized_pct": round(p.finalized_pct, 1)} for p in self.parts
            ],
        }


def part_stats(part: LoadedPart, columns: list[str]) -> PartStats:
    segments = list(part.segments.values())
    finalized = [s for s in segments if s.is_finalized]
    return PartStats(
        part_id=part.part.id,
        label=part.part.label,
        chapter=part.part.chapter,
        segments=len(segments),
        chars=sum(char_count(s.source) for s in segments),
        finalized_segments=len(finalized),
        finalized_chars=sum(char_count(s.source) for s in finalized),
        translated={c: sum(1 for s in segments if s.mt.get(c, "").strip()) for c in columns},
        orphans=list(part.orphans),
    )


def project_stats(project: Project) -> ProjectStats:
    structure = store.load_source(project.paths)
    columns = project.config.columns
    parts = [
        part_stats(store.load_part(project.paths, p.id, columns, structure), columns)
        for p in structure.parts
    ]
    return ProjectStats(project.slug, project.config.work.title, columns, parts)


def format_table(stats: ProjectStats) -> str:
    """A fixed-width table: one row per part plus a total."""
    col_heads = "".join(f" {c[:8]:>8}" for c in stats.columns)
    lines = [f"{'part':<10} {'segs':>5} {'chars':>7} {'final':>7}{col_heads}  label"]
    for p in stats.parts:
        cells = "".join(f" {p.translated[c]:>8}" for c in stats.columns)
        flag = f"  (+{len(p.orphans)} orphan)" if p.orphans else ""
        lines.append(
            f"{p.part_id:<10} {p.segments:>5} {p.chars:>7,} {p.finalized_pct:>6.1f}%{cells}  "
            f"{p.label}{flag}"
        )
    totals = "".join(f" {sum(p.translated[c] for p in stats.parts):>8}" for c in stats.columns)
    lines.append(
        f"{'total':<10} {stats.segments:>5} {stats.chars:>7,} {stats.finalized_pct:>6.1f}%{totals}"
    )
    return "\n".join(lines)
