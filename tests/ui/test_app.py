"""Smoke tests for the Streamlit pages, driven by ``streamlit.testing.v1.AppTest``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from jtw.config import ProjectConfig
from jtw.llm.base import Provider
from jtw.llm.fake import FakeProvider
from jtw.model import store
from jtw.paths import ProjectPaths

APP = str(Path(__file__).resolve().parents[2] / "src" / "jtw" / "ui" / "app.py")
COLUMNS = ["alpha", "beta"]


def _app(fake: FakeProvider | None = None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    if fake is not None:

        def factory(name: str, config: ProjectConfig) -> Provider:
            return fake

        at.session_state["provider_factory"] = factory
    return at


def test_no_projects(projects_dir: Path) -> None:
    at = _app().run()
    assert not at.exception
    assert "No projects yet" in at.info[0].value


def test_grid_shows_every_segment(worked_paths: ProjectPaths) -> None:
    at = _app().run()
    assert not at.exception, at.exception
    assert at.title[0].value == "Mini Story"
    assert len(at.checkbox) == 6  # one finalise box per segment
    finals = [t for t in at.text_area if t.key.startswith("final:")]
    assert len(finals) == 6
    assert finals[0].value == "I woke at seven..."
    assert finals[0].disabled  # finalised segments are locked
    assert "Model A" in "".join(m.value for m in at.markdown)


def test_finalise_and_save_persists(worked_paths: ProjectPaths) -> None:
    at = _app().run()
    lock = next(c for c in at.checkbox if c.key.startswith("lock:C01P01:S004"))
    lock.check().run()
    final = next(t for t in at.text_area if t.key.startswith("final:C01P01:S005"))
    final.input("There was a newspaper on the table.").run()
    save = next(b for b in at.button if b.key == "save_button")
    assert not save.disabled
    save.click().run()
    assert not at.exception, at.exception
    saved = json.loads(worked_paths.latest_save("C01P01").read_text(encoding="utf-8"))
    assert saved["segments"]["S004"]["is_finalized"] is True
    assert saved["segments"]["S005"]["final"] == "There was a newspaper on the table."
    assert saved["metadata"]["note"] == "workbench"


def test_part_switch(worked_paths: ProjectPaths) -> None:
    at = _app().run()
    at.sidebar.selectbox[1].select("C01P02").run()
    assert not at.exception
    finals = [t for t in at.text_area if t.key.startswith("final:C01P02:")]
    assert len(finals) == 6 and all(not t.value for t in finals)


def test_draft_button_uses_the_registry(worked_paths: ProjectPaths) -> None:
    fake = FakeProvider(["[S004]\nI made toast and poured tea.\n[COMMENTARY]\nSmoother."])
    at = _app(fake).run()
    next(b for b in at.button if b.key == "draft:S004").click().run()
    assert not at.exception, at.exception
    assert fake.calls and fake.calls[0].model == "fake-model-draft"
    part = store.load_part(worked_paths, "C01P01", COLUMNS)
    assert part.segments["S004"].final == "I made toast and poured tea."
    final = next(t for t in at.text_area if t.key.startswith("final:C01P01:S004"))
    assert final.value == "I made toast and poured tea."


def test_merge_toggle_and_copy(worked_paths: ProjectPaths) -> None:
    at = _app().run()
    next(b for b in at.button if b.key.startswith("merge:S001:")).click().run()
    assert any(b.key == "merge:S001:True" for b in at.button)
    next(b for b in at.button if b.key == "copy_button").click().run()
    assert not at.exception
    assert at.code[0].value.startswith("Source: 朝の七時に目が覚めた。")


def test_deep_dive_page_with_fake_provider(worked_paths: ProjectPaths) -> None:
    fake = FakeProvider(["[S006]\nI chose to walk to the station.\n[COMMENTARY]\nMore active."])
    at = _app(fake)
    at.session_state["deep_dive_target"] = ("C01P01", ["S006"])
    at.run()
    at.switch_page("pages/deep_dive_page.py").run()
    assert not at.exception, at.exception
    assert at.title[0].value == "✨ Deep Dive"
    at.text_area(key="dd_notes").input("More active, please.").run()
    at.button(key="dd_run").click().run()
    assert not at.exception, at.exception
    assert fake.calls[0].kind == "conversation" and fake.calls[0].model == "fake-model-deep"
    assert "More active." in "".join(m.value for m in at.markdown)
    at.button(key="dd_import").click().run()
    part = store.load_part(worked_paths, "C01P01", COLUMNS)
    assert part.segments["S006"].final == "I chose to walk to the station."
    assert "More active." in part.segments["S006"].notes


def test_search_page(worked_paths: ProjectPaths) -> None:
    at = _app().run()
    at.switch_page("pages/search_page.py").run()
    assert at.title[0].value == "🔎 Search"
    at.text_input(key="search_query").input("雨").run()
    assert not at.exception, at.exception
    assert at.caption[0].value == "2 match(es)"
    assert "<mark>雨</mark>" in "".join(m.value for m in at.markdown)


@pytest.mark.parametrize("bad", ["config", "source"])
def test_broken_project_is_reported(mini_paths: ProjectPaths, bad: str) -> None:
    if bad == "source":
        mini_paths.source_file.unlink()
        at = _app().run()
        assert "jtw ingest" in at.warning[0].value
    else:
        mini_paths.config_file.write_text("[work]\n", encoding="utf-8")
        at = _app().run()
        assert "No projects yet" in at.info[0].value
