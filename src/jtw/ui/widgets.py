"""Small rendering helpers shared by the pages."""

from __future__ import annotations

import html

import streamlit as st

from jtw.search import highlight_spans


def box(text: str, css_class: str, label: str | None = None) -> None:
    body = html.escape(text) if text.strip() else '<span class="jtw-empty">(empty)</span>'
    head = f'<div class="jtw-mt-label">{html.escape(label)}</div>' if label else ""
    st.markdown(f'{head}<div class="jtw-box {css_class}">{body}</div>', unsafe_allow_html=True)


def highlighted(text: str, query: str) -> str:
    return "".join(
        f"<mark>{html.escape(piece)}</mark>" if hit else html.escape(piece)
        for piece, hit in highlight_spans(text, query)
    )
