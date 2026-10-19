"""Copying a range of segments as text, for pasting into a chat with a model or an editor.

The layout comes from the ``clipboard`` template (``prompts/clipboard.txt`` by default) with
the slots ``{source}``, ``{references}``, ``{current_draft}`` and ``{comment}``. A template
line whose slots are all empty is dropped, so a segment without a comment has no
``Comment:`` line. The range is widened to whole merge chains, and each chain is copied as
one block.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Literal

from jtw.config import Project
from jtw.model.segment import Segment, key_index, merge_chains
from jtw.model.store import LoadedPart
from jtw.mt.prompts import load_template

Mode = Literal["full", "minimal"]
_SLOT_RE = re.compile(r"\{(source|references|current_draft|comment)\}")
_MINIMAL_TEMPLATE = "Source: {source}\nCurrent Draft: {current_draft}"


def render(template: str, values: Mapping[str, str]) -> str:
    lines = []
    for line in template.splitlines():
        slots = _SLOT_RE.findall(line)
        if slots and not any(values.get(slot, "").strip() for slot in slots):
            continue
        lines.append(_SLOT_RE.sub(lambda m: values.get(m.group(1), ""), line))
    return "\n".join(lines)


def chain_values(project: Project, chain: Sequence[Segment]) -> dict[str, str]:
    config = project.config
    references = []
    for column in config.columns:
        text = " ".join(s.mt.get(column, "").strip() for s in chain if s.mt.get(column, "").strip())
        references.append(f"{config.column_label(column)}: {text}")
    comments = [f"[{s.key}] {s.notes.strip()}" for s in chain if s.notes.strip()]
    return {
        "source": "".join(s.source.strip() for s in chain),
        "references": "\n".join(references),
        "current_draft": " ".join(s.final.strip() for s in chain if s.final.strip()),
        "comment": " ".join(comments),
    }


def chains_for_range(part: LoadedPart, first: str, last: str) -> list[list[Segment]]:
    """The merge chains touching ``first``..``last`` (inclusive), whole."""
    lo, hi = sorted((key_index(first), key_index(last)))
    return [
        chain
        for chain in merge_chains(list(part.segments.values()))
        if key_index(chain[-1].key) >= lo and key_index(chain[0].key) <= hi
    ]


def copy_range(
    project: Project, part: LoadedPart, first: str, last: str | None = None, mode: Mode = "full"
) -> str:
    template = _MINIMAL_TEMPLATE if mode == "minimal" else load_template(project, "clipboard")
    blocks = [
        render(template, chain_values(project, chain))
        for chain in chains_for_range(part, first, last or first)
    ]
    return "\n\n".join(blocks)


def to_system_clipboard(text: str) -> bool:
    """Copy to the OS clipboard. Returns ``False`` where no clipboard is available."""
    try:
        import pyperclip

        pyperclip.copy(text)
    except Exception:  # pyperclip raises its own exception types per platform
        return False
    return True
