"""The translation grid: source, every MT column, the translator's final text and notes."""

from __future__ import annotations

from typing import Any

import streamlit as st

from jtw.config import Project
from jtw.export.clipboard import Mode, copy_range, to_system_clipboard
from jtw.export.docx import ExportKind, export_part
from jtw.export.stats import part_stats
from jtw.llm.base import LLMError
from jtw.model.store import LoadedPart
from jtw.synth.common import SynthesisError
from jtw.synth.draft import DraftSynthesizer
from jtw.ui import state
from jtw.ui.widgets import box

REQUEST_KEY = "grid_request"
WIDTHS = [0.7, 3.2, 3.0, 2.2, 0.5]


def _request(kind: str, key: str) -> None:
    st.session_state[REQUEST_KEY] = (kind, key)


def _toggle_merge(part: LoadedPart, key: str) -> None:
    segment = part.segments[key]
    segment.merge_with_next = not segment.merge_with_next


def render() -> None:
    project = state.project()
    part_id = state.part_id()
    if project is None or part_id is None:
        st.info("Choose a project and a part in the sidebar.")
        return
    part = state.working(project, part_id)
    edit_source = bool(st.session_state.get("edit_source", False))
    state.sync_from_widgets(part, edit_source)
    _handle_request(project, part)
    part = state.working(project, part_id)

    _header(project, part)
    _toolbar(project, part)
    _grid(project, part, edit_source)


def _header(project: Project, part: LoadedPart) -> None:
    st.title(project.config.work.title)
    stats = part_stats(part, project.config.columns)
    st.caption(
        f"{part.part.label} · {stats.segments} segments · {stats.chars:,} characters · "
        f"{stats.finalized_segments} finalised"
    )
    st.progress(stats.finalized_pct / 100, text=f"{stats.finalized_pct:.1f}% finalised")
    if part.orphans:
        st.warning(
            f"{len(part.orphans)} saved segment(s) are no longer in the source: "
            f"{', '.join(part.orphans)}. They are kept at the end of the grid."
        )


def _toolbar(project: Project, part: LoadedPart) -> None:
    left, middle, right = st.columns([2, 3, 3])
    with left:
        st.toggle("Edit source text", key="edit_source")
    with middle:
        note = st.text_input("Save note", value="", placeholder="optional note", key="save_note")
        dirty = state.is_dirty(project, part)
        if st.button("💾 Save", type="primary", disabled=not dirty, key="save_button"):
            path = state.save(project, part, note or "workbench")
            st.toast(f"Saved {path.name}")
        if dirty:
            st.caption("Unsaved changes")
    with right:
        _exports(project, part)
    with st.expander("📋 Copy segments"):
        _copy_panel(project, part)


def _exports(project: Project, part: LoadedPart) -> None:
    cols = st.columns(2)
    for column, kind, label in (
        (cols[0], ExportKind.FINAL, "📄 Export final"),
        (cols[1], ExportKind.SIDE_BY_SIDE, "📄 Export J-E draft"),
    ):
        with column:
            if st.button(label, key=f"export_{kind.value}"):
                path = export_part(project, part, kind)
                st.session_state["export_file"] = (path.name, path.read_bytes())
    exported = st.session_state.get("export_file")
    if exported:
        name, data = exported
        st.download_button(f"⬇️ {name}", data=data, file_name=name, key="export_download")


def _copy_panel(project: Project, part: LoadedPart) -> None:
    keys = part.keys
    cols = st.columns([1, 1, 1, 1])
    first = cols[0].selectbox("From", keys, key="copy_first")
    last = cols[1].selectbox("To", keys, key="copy_last")
    mode: Mode = "minimal" if cols[2].toggle("Minimal", key="copy_minimal") else "full"
    if cols[3].button("Copy", key="copy_button"):
        text = copy_range(project, part, first, last, mode=mode)
        st.session_state["copied_text"] = text
        if to_system_clipboard(text):
            st.toast("Copied to the clipboard")
    if st.session_state.get("copied_text"):
        st.code(st.session_state["copied_text"], language=None)


def _grid(project: Project, part: LoadedPart, edit_source: bool) -> None:
    config = project.config
    heads = st.columns(WIDTHS)
    titles = ["Seg", "Source / machine translations", "Final", "Notes", "🔒"]
    for head, title in zip(heads, titles, strict=True):
        head.markdown(f"**{title}**")
    keys = part.keys
    for index, key in enumerate(keys):
        segment = part.segments[key]
        cols = st.columns(WIDTHS)
        with cols[0]:
            st.markdown(f"**{key}**")
            st.button(
                "🧠",
                key=f"draft:{key}",
                help="Draft from the MT columns",
                on_click=_request,
                args=("draft", key),
            )
            st.button(
                "✨",
                key=f"deep:{key}",
                help="Deep Dive revision",
                on_click=_request,
                args=("deep_dive", key),
            )
            if index < len(keys) - 1:
                st.button(
                    "⬇️" if segment.merge_with_next else "↓",
                    key=f"merge:{key}:{segment.merge_with_next}",
                    help="Unmerge from the next segment"
                    if segment.merge_with_next
                    else "Merge with the next segment in exports",
                    on_click=_toggle_merge,
                    args=(part, key),
                )
        with cols[1]:
            if edit_source:
                _area("source", key, segment.source, "Source", height=90)
            else:
                box(
                    segment.source, "jtw-source" + (" jtw-chain" if segment.merge_with_next else "")
                )
            for column in config.columns:
                box(segment.mt.get(column, ""), "jtw-mt", config.column_label(column))
        with cols[2]:
            _area("final", key, segment.final, "Final", height=160, disabled=segment.is_finalized)
        with cols[3]:
            _area("notes", key, segment.notes, "Notes", height=160)
        with cols[4]:
            lock_key = state.widget_key("lock", key)
            if lock_key not in st.session_state:
                st.session_state[lock_key] = segment.is_finalized
            st.checkbox("Finalised", key=lock_key, label_visibility="collapsed")
        st.divider()


def _area(kind: str, key: str, value: str, label: str, **kwargs: Any) -> None:
    widget = state.widget_key(kind, key)
    if widget not in st.session_state:
        st.session_state[widget] = value
    st.text_area(label, key=widget, label_visibility="collapsed", **kwargs)


def _handle_request(project: Project, part: LoadedPart) -> None:
    request = st.session_state.pop(REQUEST_KEY, None)
    if not request:
        return
    kind, key = request
    keys = state.chain_keys(part, key)
    if kind == "deep_dive":
        st.session_state["deep_dive_target"] = (part.part.id, keys)
        pages = st.session_state.get("pages", {})
        if "deep_dive" in pages:
            st.switch_page(pages["deep_dive"])
        return
    if state.is_dirty(project, part):
        state.save(project, part, "before draft")
    try:
        synth = DraftSynthesizer(project, state.registry(project))
        with st.spinner(f"Drafting {', '.join(keys)} with {synth.model}…"):
            draft = synth.generate(part, keys)
        synth.apply(draft)
    except (SynthesisError, LLMError, ValueError) as exc:
        st.error(f"Draft failed: {exc}")
        return
    state.reload(project, part.part.id)
    if draft.complete:
        st.toast(f"Drafted {', '.join(keys)}")
    else:
        st.warning(f"Draft incomplete:\n{draft.problems.describe()}")
