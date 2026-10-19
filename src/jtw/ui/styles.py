"""CSS for the workbench."""

from __future__ import annotations

CSS = """
<style>
.jtw-box {
  border: 1px solid var(--jtw-border, #d0d7de);
  border-radius: 6px;
  padding: 0.45rem 0.6rem;
  margin-bottom: 0.4rem;
  white-space: pre-wrap;
  line-height: 1.5;
}
.jtw-source { background: rgba(127, 127, 127, 0.08); font-size: 1.05rem; }
.jtw-mt { background: rgba(33, 150, 243, 0.06); }
.jtw-mt-label { font-size: 0.75rem; opacity: 0.7; margin-bottom: 0.1rem; }
.jtw-empty { opacity: 0.45; font-style: italic; }
.jtw-chain { border-left: 3px solid #f0a500; padding-left: 0.4rem; }
mark { background: #ffe066; padding: 0 0.1rem; }
</style>
"""
