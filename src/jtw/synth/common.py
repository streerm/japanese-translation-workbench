"""Pieces shared by the draft synthesiser and Deep Dive."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from jtw.config import Project
from jtw.model import store
from jtw.model.segment import Segment
from jtw.mt.prompts import render_glossary


class SynthesisError(RuntimeError):
    """The model's reply could not be used at all."""


def common_slots(project: Project) -> dict[str, object]:
    config = project.config
    return {
        "work_title": config.work.title,
        "style_notes": config.prompts.style_notes.strip() or "(none)",
        "glossary": render_glossary(config.glossary),
    }


def render_references(
    project: Project,
    segments: Mapping[str, Segment],
    keys: Sequence[str],
    *,
    include_final: bool,
) -> str:
    """Each segment's source, current draft and machine translations, under its key."""
    config = project.config
    blocks = []
    for key in keys:
        segment = segments[key]
        lines = [f"[{key}]", f"Japanese: {segment.source}"]
        if include_final:
            lines.append(f"Current draft: {segment.final.strip() or '(none yet)'}")
        for column in config.columns:
            text = segment.mt.get(column, "").strip()
            if text:
                lines.append(f"Reference ({config.column_label(column)}): {text}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def range_label(keys: Sequence[str]) -> str:
    return keys[0] if len(keys) == 1 else f"{keys[0]}–{keys[-1]}"


def write_finals(
    project: Project,
    part_id: str,
    finals: Mapping[str, str],
    *,
    commentary: str = "",
    commentary_heading: str = "",
    note: str = "",
) -> None:
    """Write ``final`` text for the given keys and append commentary to the first key's notes.

    The part is re-read first so concurrent edits elsewhere survive.
    """
    if not finals:
        return
    loaded = store.load_part(project.paths, part_id, project.config.columns)
    for key, text in finals.items():
        loaded.segments[key].final = text
    if commentary.strip():
        first = loaded.segments[next(iter(finals))]
        entry = f"{commentary_heading}\n{commentary.strip()}" if commentary_heading else commentary
        first.notes = f"{first.notes.rstrip()}\n\n{entry}".strip()
    store.save_part(
        project.paths, part_id, loaded.segments, note=note, keep=project.config.limits.keep_saves
    )
