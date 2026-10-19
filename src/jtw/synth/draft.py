"""Drafting a combined translation from a segment's source and its MT columns."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from jtw.config import Project
from jtw.llm.registry import Registry
from jtw.model.store import LoadedPart
from jtw.mt.prompts import SYSTEM_PROMPT, fill, load_template
from jtw.mt.protocol import ParseProblems, parse_response, split_commentary
from jtw.synth.common import (
    SynthesisError,
    common_slots,
    range_label,
    render_references,
    write_finals,
)


@dataclass
class DraftResult:
    part_id: str
    keys: list[str]
    drafts: dict[str, str]
    commentary: str
    problems: ParseProblems
    model: str

    @property
    def complete(self) -> bool:
        return not self.problems


class DraftSynthesizer:
    def __init__(self, project: Project, registry: Registry) -> None:
        self._project = project
        self._route = registry.draft()
        self._template = load_template(project, "draft")

    @property
    def model(self) -> str:
        return self._route.model

    def build_prompt(self, part: LoadedPart, keys: Sequence[str]) -> str:
        return fill(
            self._template,
            **common_slots(self._project),
            segments=render_references(self._project, part.segments, keys, include_final=False),
            segment_count=len(keys),
        )

    def generate(self, part: LoadedPart, keys: Sequence[str]) -> DraftResult:
        """Ask the draft model for every key. Raises :class:`SynthesisError` if nothing parsed."""
        keys = list(keys)
        if not keys:
            raise ValueError("no segments to draft")
        result = self._route.complete(
            self.build_prompt(part, keys),
            system=SYSTEM_PROMPT,
            max_tokens=self._project.config.limits.max_tokens_default,
        )
        body, commentary = split_commentary(result.text)
        parsed = parse_response(body, keys)
        if not parsed.translations:
            raise SynthesisError(f"the draft could not be parsed:\n{parsed.problems.describe()}")
        return DraftResult(
            part.part.id, keys, parsed.translations, commentary, parsed.problems, result.model
        )

    def apply(self, draft: DraftResult) -> None:
        """Write the drafts into ``final`` and the commentary into the notes."""
        write_finals(
            self._project,
            draft.part_id,
            draft.drafts,
            commentary=draft.commentary,
            commentary_heading=f"Draft notes ({range_label(draft.keys)}):",
            note=f"draft {range_label(draft.keys)}",
        )
