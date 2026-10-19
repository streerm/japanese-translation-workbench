from __future__ import annotations

import json

import pytest
from tests.helpers import requested_keys

from jtw.config import Project, load_project
from jtw.llm.base import ModelMismatch
from jtw.llm.fake import FakeProvider
from jtw.llm.registry import Registry, build_registry
from jtw.model import store
from jtw.mt.protocol import split_commentary
from jtw.paths import ProjectPaths
from jtw.synth.common import SynthesisError, write_finals
from jtw.synth.deep_dive import DeepDiveSession, session_path
from jtw.synth.draft import DraftSynthesizer


@pytest.fixture
def project(mini_paths: ProjectPaths) -> Project:
    project = load_project("mini")
    loaded = store.load_part(project.paths, "C01P01", project.config.columns)
    for key, segment in loaded.segments.items():
        segment.mt["alpha"] = f"alpha {key}"
        if key != "S003":
            segment.mt["beta"] = f"beta {key}"
    loaded.segments["S002"].final = "Existing draft two."
    loaded.segments["S002"].notes = "Check the weather word."
    store.save_part(project.paths, "C01P01", loaded.segments)
    return project


def _registry(project: Project, fake: FakeProvider) -> Registry:
    return build_registry(project.config, lambda name, cfg: fake)


def _part(project: Project) -> store.LoadedPart:
    return store.load_part(project.paths, "C01P01", project.config.columns)


def test_split_commentary() -> None:
    assert split_commentary("[S001]\nA.\n\n**[COMMENTARY]:**\nWhy.\n```") == (
        "[S001]\nA.\n\n",
        "Why.",
    )
    assert split_commentary("[S001]\nA.") == ("[S001]\nA.", "")
    assert split_commentary("[S001]\nA.\n## [commentary]\nx")[1] == "x"


# --- draft -------------------------------------------------------------------


def test_draft_prompt_uses_configured_columns(project: Project) -> None:
    synth = DraftSynthesizer(project, _registry(project, FakeProvider()))
    prompt = synth.build_prompt(_part(project), ["S002", "S003"])
    assert "Reference (Model A): alpha S002" in prompt
    assert "Reference (Model B): beta S002" in prompt
    assert "beta S003" not in prompt  # blank columns are left out
    assert "Current draft" not in prompt
    assert requested_keys(prompt) == ["S002", "S003"]
    assert "Return all 2 key(s)" in prompt
    assert synth.model == "fake-model-draft"


def test_draft_parses_multi_segment_reply_and_applies(project: Project) -> None:
    reply = "Here:\n[S001]\nI woke at seven.\n\n[S002]\nRain fell.\n\n[COMMENTARY]\nKept it plain."
    fake = FakeProvider([reply])
    synth = DraftSynthesizer(project, _registry(project, fake))
    draft = synth.generate(_part(project), ["S001", "S002"])
    assert fake.calls[0].model == "fake-model-draft"
    assert draft.complete
    assert draft.drafts == {"S001": "I woke at seven.", "S002": "Rain fell."}
    assert draft.commentary == "Kept it plain."

    synth.apply(draft)
    part = _part(project)
    assert part.segments["S001"].final == "I woke at seven."
    assert part.segments["S002"].final == "Rain fell."
    assert part.segments["S001"].notes == "Draft notes (S001–S002):\nKept it plain."
    assert part.segments["S002"].notes == "Check the weather word."
    assert part.segments["S001"].mt["alpha"] == "alpha S001"


def test_draft_partial_and_failed(project: Project) -> None:
    fake = FakeProvider(["[S001]\nOnly one.", "Sorry, no."])
    synth = DraftSynthesizer(project, _registry(project, fake))
    partial = synth.generate(_part(project), ["S001", "S002"])
    assert not partial.complete and partial.drafts == {"S001": "Only one."}
    with pytest.raises(SynthesisError, match="no \\[Snnn\\]"):
        synth.generate(_part(project), ["S001"])
    with pytest.raises(ValueError):
        synth.generate(_part(project), [])


def test_draft_model_guard(project: Project) -> None:
    fake = FakeProvider(["[S001]\nX."], served_model="someone-else")
    with pytest.raises(ModelMismatch):
        DraftSynthesizer(project, _registry(project, fake)).generate(_part(project), ["S001"])


# --- deep dive ---------------------------------------------------------------


def test_deep_dive_iterations_persist_and_continue_the_conversation(project: Project) -> None:
    fake = FakeProvider(
        [
            '[S002]\nRain fell softly.\n[S003]\n"Morning," my sister said.\n[COMMENTARY]\nFirst.',
            "[S002]\nA soft rain was falling.\n[COMMENTARY]\nSecond.",
        ]
    )
    registry = _registry(project, fake)
    session = DeepDiveSession.open(project, registry, "C01P01", ["S002", "S003"])
    assert session.label == "C01P01 S002–S003" and session.latest is None
    first = session.start("Make it gentler.")
    assert first.revisions["S002"] == "Rain fell softly." and first.commentary == "First."

    call = fake.calls[0]
    assert call.kind == "conversation" and call.model == "fake-model-deep"
    assert "Current draft: Existing draft two." in call.prompt
    assert "Current draft: (none yet)" in call.prompt
    assert "Make it gentler." in call.prompt

    path = session_path(project.paths, "C01P01", ["S002", "S003"])
    assert path.name == "deep_dive_C01P01_S002-S003.json" and path.exists()

    resumed = DeepDiveSession.open(project, registry, "C01P01", ["S002", "S003"])
    second = resumed.iterate("Less literal.")
    assert len(fake.calls[1].messages) == 3  # user, assistant, user
    assert fake.calls[1].messages[1]["content"].startswith("[S002]")
    assert "Less literal." in fake.calls[1].prompt
    assert second.problems == "keys not returned at all: S003"
    assert resumed.current_revisions() == {
        "S002": "A soft rain was falling.",
        "S003": '"Morning," my sister said.',
    }

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["part_id"] == "C01P01" and saved["keys"] == ["S002", "S003"]
    assert [it["notes"] for it in saved["iterations"]] == ["Make it gentler.", "Less literal."]
    assert set(saved["iterations"][0]) == {
        "notes",
        "response",
        "revisions",
        "commentary",
        "problems",
    }
    assert len(saved["messages"]) == 4


def test_deep_dive_import_writes_exactly_final_and_notes(project: Project) -> None:
    fake = FakeProvider(["[S002]\nRevised two.\n[COMMENTARY]\nTightened."])
    session = DeepDiveSession.open(project, _registry(project, fake), "C01P01", ["S002"])
    with pytest.raises(SynthesisError, match="nothing to import"):
        session.import_to_part()
    session.iterate("tighten")  # iterate with no history starts
    before = _part(project).segments
    written = session.import_to_part()
    after = _part(project).segments
    assert written == {"S002": "Revised two."}
    assert after["S002"].final == "Revised two."
    assert after["S002"].notes == "Check the weather word.\n\nDeep Dive (S002):\nTightened."
    for key in before:
        for field in ("source", "mt", "is_finalized", "merge_with_next"):
            assert getattr(after[key], field) == getattr(before[key], field)
        if key != "S002":
            assert after[key] == before[key]
    session.discard()
    assert not session.path.exists() and session.latest is None


def test_deep_dive_errors(project: Project) -> None:
    registry = _registry(project, FakeProvider(["no markers here"]))
    with pytest.raises(ValueError):
        DeepDiveSession.open(project, registry, "C01P01", [])
    with pytest.raises(KeyError, match="S042"):
        DeepDiveSession.open(project, registry, "C01P01", ["S042"]).start("x")
    session = DeepDiveSession.open(project, registry, "C01P01", ["S001"])
    with pytest.raises(SynthesisError):
        session.start("")
    assert not session.path.exists()
    assert session.model == "fake-model-deep"


def test_write_finals_noop(project: Project) -> None:
    before = store.list_saves(project.paths, "C01P01")
    write_finals(project, "C01P01", {})
    assert store.list_saves(project.paths, "C01P01") == before
