"""The Search page: bilingual search across every part."""

from __future__ import annotations

import streamlit as st

from jtw.search import guess_lang, search
from jtw.ui import state
from jtw.ui.widgets import highlighted


def _open(part_id: str) -> None:
    state.set_part(part_id)
    st.session_state["switch_to_grid"] = True


def render() -> None:
    st.title("🔎 Search")
    project = state.project()
    if project is None:
        st.info("Choose a project in the sidebar.")
        return
    if st.session_state.pop("switch_to_grid", False):
        pages = st.session_state.get("pages", {})
        if "grid" in pages:
            st.switch_page(pages["grid"])
    cols = st.columns([4, 2, 1])
    query = cols[0].text_input("Find", key="search_query", placeholder="雨 / rain")
    lang = cols[1].radio("In", ["auto", "ja", "en", "both"], horizontal=True, key="search_lang")
    context = int(cols[2].number_input("Context", 0, 5, 1, key="search_context"))
    if not query.strip():
        return
    chosen = guess_lang(query) if lang == "auto" else lang
    hits = search(project, query, lang=chosen, context=context)  # type: ignore[arg-type]
    st.caption(f"{len(hits)} match(es)")
    config = project.config
    for i, hit in enumerate(hits):
        with st.container(border=True):
            head, button = st.columns([5, 1])
            head.markdown(f"**{hit.ref}** · {hit.part_label} · in {', '.join(hit.fields)}")
            button.button("Open", key=f"open:{i}", on_click=_open, args=(hit.part_id,))
            for neighbour in hit.before:
                st.caption(f"{neighbour.key} {neighbour.source}")
            seg = hit.segment
            lines = [highlighted(seg.source, query)]
            if seg.final:
                lines.append(highlighted(seg.final, query))
            for column in hit.fields:
                if column in seg.mt:
                    label = config.column_label(column)
                    lines.append(f"<small>{label}</small> {highlighted(seg.mt[column], query)}")
            st.markdown("<br>".join(lines), unsafe_allow_html=True)
            for neighbour in hit.after:
                st.caption(f"{neighbour.key} {neighbour.source}")
