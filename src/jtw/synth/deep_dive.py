"""Deep Dive: iterative revision of a few segments against the translator's notes.

A session covers a consecutive range of keys in one part. The first iteration sends the
source, the current draft and the MT references with the translator's notes; each further
iteration continues the same conversation with new notes. The session is saved to
``<project>/tmp/deep_dive_<part>_<first>-<last>.json`` after every iteration, so closing the
browser loses nothing. "Import to main" writes the latest revision into ``final`` and appends
the commentary to the notes.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from jtw.config import Project
from jtw.llm.base import Message
from jtw.llm.registry import Registry
from jtw.model import store
from jtw.mt.prompts import fill, load_template
from jtw.mt.protocol import parse_response, split_commentary
from jtw.paths import ProjectPaths
from jtw.synth.common import (
    SynthesisError,
    common_slots,
    range_label,
    render_references,
    write_finals,
)

SCHEMA_VERSION = 1
DEEP_DIVE_SYSTEM = (
    "You are an expert literary translation editor working with a Japanese-to-English "
    "translator. You follow output format instructions exactly."
)
_FOLLOW_UP = """The translator has new notes on your latest revision:

{notes}

Revise again. Return every key ({keys}) in the same format as before, then [COMMENTARY]."""


@dataclass
class Iteration:
    notes: str
    response: str
    revisions: dict[str, str]
    commentary: str
    problems: str = ""


@dataclass
class DeepDiveState:
    part_id: str
    keys: list[str]
    iterations: list[Iteration] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA_VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeepDiveState:
        return cls(
            part_id=str(data["part_id"]),
            keys=[str(k) for k in data["keys"]],
            iterations=[Iteration(**it) for it in data.get("iterations", [])],
            messages=[
                Message(role=m["role"], content=m["content"]) for m in data.get("messages", [])
            ],
        )


def session_path(paths: ProjectPaths, part_id: str, keys: Sequence[str]) -> Path:
    return paths.tmp / f"deep_dive_{part_id}_{keys[0]}-{keys[-1]}.json"


class DeepDiveSession:
    """One Deep Dive over ``keys`` of ``part_id``. Use :meth:`open` to resume a saved one."""

    def __init__(self, project: Project, registry: Registry, state: DeepDiveState) -> None:
        if not state.keys:
            raise ValueError("a Deep Dive needs at least one segment")
        self._project = project
        self._route = registry.deep_dive()
        self.state = state

    @classmethod
    def open(
        cls, project: Project, registry: Registry, part_id: str, keys: Sequence[str]
    ) -> DeepDiveSession:
        keys = list(keys)
        path = session_path(project.paths, part_id, keys) if keys else None
        if path is not None and path.exists():
            state = DeepDiveState.from_dict(json.loads(path.read_text(encoding="utf-8")))
        else:
            state = DeepDiveState(part_id, keys)
        return cls(project, registry, state)

    # --- properties ---------------------------------------------------------

    @property
    def path(self) -> Path:
        return session_path(self._project.paths, self.state.part_id, self.state.keys)

    @property
    def model(self) -> str:
        return self._route.model

    @property
    def label(self) -> str:
        return f"{self.state.part_id} {range_label(self.state.keys)}"

    @property
    def latest(self) -> Iteration | None:
        return self.state.iterations[-1] if self.state.iterations else None

    def current_revisions(self) -> dict[str, str]:
        """The newest revision of each key across all iterations."""
        merged: dict[str, str] = {}
        for iteration in self.state.iterations:
            merged.update(iteration.revisions)
        return merged

    # --- iterations ---------------------------------------------------------

    def start(self, notes: str) -> Iteration:
        """The first iteration. Starting again discards earlier iterations."""
        part = store.load_part(
            self._project.paths, self.state.part_id, self._project.config.columns
        )
        missing = [k for k in self.state.keys if k not in part.segments]
        if missing:
            raise KeyError(f"{self.state.part_id} has no segment(s) {', '.join(missing)}")
        prompt = fill(
            load_template(self._project, "deep_dive"),
            **common_slots(self._project),
            segments=render_references(
                self._project, part.segments, self.state.keys, include_final=True
            ),
            segment_count=len(self.state.keys),
            notes=notes.strip() or "(no notes: improve the draft as you see fit)",
        )
        self.state.iterations = []
        self.state.messages = []
        return self._exchange(prompt, notes)

    def iterate(self, notes: str) -> Iteration:
        if not self.state.iterations:
            return self.start(notes)
        message = _FOLLOW_UP.format(
            notes=notes.strip() or "(no new notes)", keys=", ".join(self.state.keys)
        )
        return self._exchange(message, notes)

    def _exchange(self, user_message: str, notes: str) -> Iteration:
        messages: list[Message] = [*self.state.messages, {"role": "user", "content": user_message}]
        result = self._route.conversation(
            messages,
            system=DEEP_DIVE_SYSTEM,
            max_tokens=self._project.config.limits.max_tokens_default,
        )
        body, commentary = split_commentary(result.text)
        parsed = parse_response(body, self.state.keys)
        if not parsed.translations:
            raise SynthesisError(f"the revision could not be parsed:\n{parsed.problems.describe()}")
        iteration = Iteration(
            notes=notes,
            response=result.text,
            revisions=parsed.translations,
            commentary=commentary,
            problems=parsed.problems.describe(),
        )
        self.state.messages = [*messages, {"role": "assistant", "content": result.text}]
        self.state.iterations.append(iteration)
        self.save()
        return iteration

    # --- persistence --------------------------------------------------------

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.state.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return self.path

    def discard(self) -> None:
        self.path.unlink(missing_ok=True)
        self.state.iterations = []
        self.state.messages = []

    def import_to_part(self) -> dict[str, str]:
        """Write the newest revisions into ``final`` and the latest commentary into the notes.

        Returns what was written. The session file is left in place until :meth:`discard`.
        """
        latest = self.latest
        if latest is None:
            raise SynthesisError("nothing to import: run an iteration first")
        revisions = self.current_revisions()
        write_finals(
            self._project,
            self.state.part_id,
            revisions,
            commentary=latest.commentary,
            commentary_heading=f"Deep Dive ({range_label(self.state.keys)}):",
            note=f"deep dive import {range_label(self.state.keys)}",
        )
        return revisions
