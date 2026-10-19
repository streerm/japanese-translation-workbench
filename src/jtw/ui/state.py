"""Session-state helpers: which project and part are open, and the working copy of a part.

The working copy is the part as loaded from disk plus whatever the translator has typed
since. Widget keys carry a *generation* number that changes whenever the part is reloaded
from disk, so stale widget values never leak into a freshly loaded part.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import streamlit as st

from jtw.config import Project, load_project
from jtw.llm.registry import ProviderFactory, Registry, build_registry, default_factory
from jtw.model import store
from jtw.model.part import Structure
from jtw.model.segment import Segment
from jtw.model.store import LoadedPart

PROJECT_ENV = "JTW_PROJECT"
#: Tests and offline demos put a provider factory here to keep the UI off the network.
FACTORY_KEY = "provider_factory"


def _state() -> Any:
    return st.session_state


def registry(project: Project) -> Registry:
    factory: ProviderFactory = _state().get(FACTORY_KEY, default_factory)
    return build_registry(project.config, factory)


def default_slug(slugs: list[str]) -> str | None:
    wanted = _state().get("project_slug") or os.environ.get(PROJECT_ENV)
    if wanted in slugs:
        return str(wanted)
    return slugs[0] if slugs else None


def set_project(slug: str) -> None:
    if _state().get("project_slug") != slug:
        _state()["project_slug"] = slug
        _state().pop("part_id", None)
        _drop_working_copy()


def project() -> Project | None:
    slug = _state().get("project_slug")
    return load_project(slug) if slug else None


def structure(project: Project) -> Structure:
    return store.load_source(project.paths)


def set_part(part_id: str) -> None:
    if _state().get("part_id") != part_id:
        _state()["part_id"] = part_id
        _drop_working_copy()


def part_id() -> str | None:
    value = _state().get("part_id")
    return str(value) if value else None


def _drop_working_copy() -> None:
    _state().pop("working", None)


def working(project: Project, part: str) -> LoadedPart:
    """The working copy of ``part``, loading it from disk the first time."""
    current = _state().get("working")
    if current is None or current.part.id != part:
        current = store.load_part(project.paths, part, project.config.columns)
        _state()["working"] = current
        _state()["generation"] = _state().get("generation", 0) + 1
    return current  # type: ignore[no-any-return]


def reload(project: Project, part: str) -> LoadedPart:
    _drop_working_copy()
    return working(project, part)


def widget_key(kind: str, segment_key: str) -> str:
    return f"{kind}:{_state().get('part_id')}:{segment_key}:{_state().get('generation', 0)}"


def sync_from_widgets(part: LoadedPart, edit_source: bool) -> None:
    """Copy current widget values into the working copy."""
    state = _state()
    for key, segment in part.segments.items():
        segment.final = state.get(widget_key("final", key), segment.final)
        segment.notes = state.get(widget_key("notes", key), segment.notes)
        segment.is_finalized = bool(state.get(widget_key("lock", key), segment.is_finalized))
        if edit_source:
            segment.source = state.get(widget_key("source", key), segment.source)


def is_dirty(project: Project, part: LoadedPart) -> bool:
    on_disk = store.load_part(project.paths, part.part.id, project.config.columns)
    return on_disk.segments != part.segments


def save(project: Project, part: LoadedPart, note: str = "workbench") -> Path:
    return store.save_part(
        project.paths,
        part.part.id,
        part.segments,
        note=note,
        keep=project.config.limits.keep_saves,
    )


def chain_keys(part: LoadedPart, key: str) -> list[str]:
    """The keys of the merge chain containing ``key``."""
    from jtw.model.segment import merge_chains

    for chain in merge_chains(list(part.segments.values())):
        keys = [s.key for s in chain]
        if key in keys:
            return keys
    return [key]


def segment(part: LoadedPart, key: str) -> Segment:
    return part.segments[key]
