"""Prompt templates and the slots they are filled with.

Templates are Markdown files with ``{slot}`` placeholders. Defaults live in the repository's
``prompts/`` directory; a project can point any template at its own file in ``project.toml``
(``[prompts] translate = "prompts/translate.md"``). Only known slot names are substituted, so a
template may contain other braces freely.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from jtw.config import Project
from jtw.model.part import Part
from jtw.mt.protocol import render_segments
from jtw.resources import default_prompts_dir
from jtw.text.ja import char_count

TemplateName = Literal["translate", "repair", "draft", "deep_dive", "clipboard"]
_FILENAMES: dict[TemplateName, str] = {
    "translate": "translate.md",
    "repair": "repair.md",
    "draft": "draft.md",
    "deep_dive": "deep_dive.md",
    "clipboard": "clipboard.txt",
}
SLOTS = frozenset(
    {
        "work_title",
        "part_header",
        "style_notes",
        "glossary",
        "segments",
        "segment_count",
        "problem",
        "references",
        "notes",
    }
)
_SLOT_RE = re.compile(r"\{([a-z_]+)\}")

SYSTEM_PROMPT = (
    "You are a professional Japanese-to-English literary translator. "
    "You follow output format instructions exactly."
)


def template_path(project: Project, name: TemplateName) -> Path:
    override: str | None = getattr(project.config.prompts, name)
    if override:
        return project.paths.root / override
    return default_prompts_dir() / _FILENAMES[name]


def load_template(project: Project, name: TemplateName) -> str:
    path = template_path(project, name)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"prompt template {name!r} not found at {path}") from None


def fill(template: str, **slots: object) -> str:
    """Substitute ``{slot}`` placeholders. Unknown names and unsupplied slots are left alone."""
    unknown = set(slots) - SLOTS
    if unknown:
        raise ValueError(f"unknown prompt slots: {', '.join(sorted(unknown))}")

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return str(slots[name]) if name in slots else match.group(0)

    return _SLOT_RE.sub(replace, template)


def render_glossary(glossary: Mapping[str, str]) -> str:
    if not glossary:
        return "(none)"
    return "\n".join(f"- {source} → {target}" for source, target in glossary.items())


def part_header(part: Part, position: int, total: int, sources: Mapping[str, str]) -> str:
    """``**Part 2 of 7** (Chapter 1 · Part 2): 6 segments, 120 characters, S001–S006``."""
    keys = list(sources)
    chars = sum(char_count(text) for text in sources.values())
    span = f"{keys[0]}–{keys[-1]}" if len(keys) > 1 else keys[0]
    return (
        f"**Part {position} of {total}** ({part.label}): {len(keys)} segment(s), "
        f"{chars:,} characters, {span}"
    )


class PromptBuilder:
    """Renders the translation and repair prompts for one project."""

    def __init__(self, project: Project) -> None:
        self._project = project
        self._translate = load_template(project, "translate")
        self._repair = load_template(project, "repair")

    def _common(self) -> dict[str, object]:
        config = self._project.config
        return {
            "work_title": config.work.title,
            "style_notes": config.prompts.style_notes.strip() or "(none)",
            "glossary": render_glossary(config.glossary),
        }

    def translate(self, part: Part, position: int, total: int, keys: Sequence[str]) -> str:
        sources = {key: part.source_text(key) for key in keys}
        return fill(
            self._translate,
            **self._common(),
            part_header=part_header(part, position, total, sources),
            segments=render_segments(sources),
            segment_count=len(keys),
        )

    def repair(
        self, part: Part, position: int, total: int, keys: Sequence[str], problem: str
    ) -> str:
        sources = {key: part.source_text(key) for key in keys}
        return fill(
            self._repair,
            **self._common(),
            part_header=part_header(part, position, total, sources),
            segments=render_segments(sources),
            segment_count=len(keys),
            problem=problem,
        )
