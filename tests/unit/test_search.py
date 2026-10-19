import pytest

from jtw.config import Project, load_project
from jtw.paths import ProjectPaths
from jtw.search import guess_lang, highlight, highlight_spans, search


@pytest.fixture
def project(worked_paths: ProjectPaths) -> Project:
    return load_project("mini")


def test_japanese_search_hits_source_with_context(project: Project) -> None:
    hits = search(project, "雨", lang="ja")
    assert [h.ref for h in hits] == ["C01P01/S002", "C01P02/S006"]
    first = hits[0]
    assert first.fields == ["source"]
    assert [s.key for s in first.before] == ["S001"]
    assert [s.key for s in first.after] == ["S003"]
    assert hits[1].after == []
    assert first.part_label == "Chapter 1 · Part 1"


def test_english_search_is_case_insensitive_and_covers_columns(project: Project) -> None:
    hits = search(project, "ALPHA s004", lang="en")
    assert [(h.ref, h.fields) for h in hits] == [("C01P01/S004", ["alpha"])]
    hits = search(project, "sister", lang="en", context=0)
    assert [(h.ref, h.fields) for h in hits] == [("C01P01/S003", ["final", "notes"])]
    assert hits[0].before == [] and hits[0].after == []


def test_both_and_empty(project: Project) -> None:
    assert search(project, "  ") == []
    assert search(project, "雨", lang="en") == []
    assert len(search(project, "雨")) == 2


def test_guess_lang_and_highlight() -> None:
    assert guess_lang("駅") == "ja" and guess_lang("station") == "en"
    assert highlight("Rain, rain", "rain") == "**Rain**, **rain**"
    assert list(highlight_spans("abc", "")) == [("abc", False)]
    assert list(highlight_spans("xab", "ab")) == [("x", False), ("ab", True)]
