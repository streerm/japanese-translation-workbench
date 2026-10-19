"""The Deep Dive page: iterate on a few segments with the Deep Dive model, then import."""

from __future__ import annotations

import streamlit as st

from jtw.config import Project
from jtw.llm.base import LLMError
from jtw.synth.common import SynthesisError
from jtw.synth.deep_dive import DeepDiveSession
from jtw.ui import state
from jtw.ui.widgets import box


def _back_to_grid() -> None:
    pages = st.session_state.get("pages", {})
    if "grid" in pages:
        st.switch_page(pages["grid"])


def render() -> None:
    project = state.project()
    target = st.session_state.get("deep_dive_target")
    st.title("✨ Deep Dive")
    if project is None or not target:
        st.info("Open a Deep Dive from a segment's ✨ button in the grid.")
        return
    part_id, keys = target
    session = DeepDiveSession.open(project, state.registry(project), part_id, keys)
    st.caption(
        f"{session.label} · model {session.model} · {len(session.state.iterations)} iteration(s)"
    )

    _segments(project, session)
    _controls(project, session)
    _history(session)


def _segments(project: Project, session: DeepDiveSession) -> None:
    part = state.working(project, session.state.part_id)
    revisions = session.current_revisions()
    for key in session.state.keys:
        segment = part.segments[key]
        st.markdown(f"**{key}**")
        left, middle, right = st.columns(3)
        with left:
            box(segment.source, "jtw-source", "Source")
        with middle:
            box(segment.final, "jtw-mt", "Current final")
        with right:
            box(revisions.get(key, ""), "jtw-mt", "Latest revision")
    latest = session.latest
    if latest and latest.commentary:
        st.markdown("**Commentary**")
        st.markdown(latest.commentary)
    if latest and latest.problems:
        st.warning(latest.problems)


def _controls(project: Project, session: DeepDiveSession) -> None:
    notes = st.text_area("Your notes for the next revision", key="dd_notes", height=140)
    cols = st.columns(4)
    label = "Run first revision" if not session.state.iterations else "Iterate"
    if cols[0].button(label, type="primary", key="dd_run"):
        part = state.working(project, session.state.part_id)
        if state.is_dirty(project, part):
            state.save(project, part, "before deep dive")
        try:
            with st.spinner(f"{session.model} is revising…"):
                session.iterate(notes)
        except (SynthesisError, LLMError, ValueError, KeyError) as exc:
            st.error(f"Revision failed: {exc}")
        else:
            st.rerun()
    if cols[1].button("📥 Import to main", disabled=session.latest is None, key="dd_import"):
        part = state.working(project, session.state.part_id)
        if state.is_dirty(project, part):
            state.save(project, part, "before deep dive import")
        session.import_to_part()
        session.discard()
        state.reload(project, session.state.part_id)
        st.session_state.pop("deep_dive_target", None)
        st.toast(f"Imported {session.label}")
        _back_to_grid()
    if cols[2].button("🗑️ Discard session", disabled=session.latest is None, key="dd_discard"):
        session.discard()
        st.rerun()
    if cols[3].button("↩️ Back to grid", key="dd_back"):
        _back_to_grid()


def _history(session: DeepDiveSession) -> None:
    if not session.state.iterations:
        return
    with st.expander(f"History ({len(session.state.iterations)})"):
        for number, iteration in enumerate(session.state.iterations, start=1):
            st.markdown(f"**Iteration {number}**: {iteration.notes or '(no notes)'}")
            for key, text in iteration.revisions.items():
                st.markdown(f"- `{key}` {text}")
            if iteration.commentary:
                st.caption(iteration.commentary)
