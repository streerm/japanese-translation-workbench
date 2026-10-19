"""Streamlit entry point. Launch with ``jtw serve`` (or ``streamlit run src/jtw/ui/app.py``)."""

from __future__ import annotations

import streamlit as st

from jtw.config import ConfigError
from jtw.model.store import StoreError
from jtw.projects import discover
from jtw.ui import state
from jtw.ui.styles import CSS


def _sidebar() -> bool:
    """Project and part pickers. Returns ``False`` if there is nothing to show yet."""
    st.sidebar.title("Translation workbench")
    projects = [p for p in discover() if p.error is None]
    slugs = [p.slug for p in projects]
    chosen = state.default_slug(slugs)
    if chosen is None:
        st.info("No projects yet. Create one with `jtw new <slug>` and `jtw ingest`.")
        return False
    titles = {p.slug: p.title for p in projects}
    slug = st.sidebar.selectbox(
        "Project", slugs, index=slugs.index(chosen), format_func=lambda s: f"{titles[s]} ({s})"
    )
    state.set_project(slug)
    project = state.project()
    assert project is not None
    try:
        structure = state.structure(project)
    except StoreError as exc:
        st.warning(str(exc))
        return False

    labels = {
        p.id: p.label + (f" — {p.chapter_title}" if p.chapter_title else "")
        for p in structure.parts
    }
    current = state.part_id()
    index = structure.ids.index(current) if current in structure.ids else 0
    part = st.sidebar.selectbox(
        "Part", structure.ids, index=index, format_func=lambda pid: labels[pid]
    )
    if part is not None:
        state.set_part(part)
    return True


def main() -> None:
    st.set_page_config(page_title="Translation workbench", page_icon="📖", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    # File-based pages (rather than callables) so AppTest can switch between them.
    pages = {
        "grid": st.Page(
            "pages/grid_page.py", title="Grid", icon="📖", url_path="grid", default=True
        ),
        "deep_dive": st.Page(
            "pages/deep_dive_page.py", title="Deep Dive", icon="✨", url_path="deep-dive"
        ),
        "search": st.Page("pages/search_page.py", title="Search", icon="🔎", url_path="search"),
    }
    st.session_state["pages"] = pages
    navigation = st.navigation(list(pages.values()))
    try:
        ready = _sidebar()
    except ConfigError as exc:
        st.error(str(exc))
        return
    if ready:
        navigation.run()


main()
