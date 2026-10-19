from pathlib import Path

import pytest
from tests.helpers import requested_keys

from jtw.config import Project, load_project
from jtw.model.store import load_source
from jtw.mt.prompts import (
    PromptBuilder,
    fill,
    load_template,
    part_header,
    render_glossary,
    template_path,
)
from jtw.paths import ProjectPaths
from jtw.resources import default_prompts_dir


@pytest.fixture
def project(mini_paths: ProjectPaths) -> Project:
    return load_project("mini")


def test_fill_only_known_slots() -> None:
    assert fill("{work_title} {other} {{x}}", work_title="T") == "T {other} {{x}}"
    assert fill("{problem}") == "{problem}"
    with pytest.raises(ValueError, match="unknown prompt slots: nope"):
        fill("", nope=1)


def test_render_glossary() -> None:
    assert render_glossary({}) == "(none)"
    assert render_glossary({"姉": "my sister", "駅": "the station"}) == (
        "- 姉 → my sister\n- 駅 → the station"
    )


def test_default_and_override_paths(project: Project) -> None:
    assert template_path(project, "translate") == default_prompts_dir() / "translate.md"
    custom = project.paths.root / "prompts" / "translate.md"
    custom.parent.mkdir()
    custom.write_text("CUSTOM {work_title}", encoding="utf-8")
    text = project.paths.config_file.read_text(encoding="utf-8")
    project.paths.config_file.write_text(
        text.replace("[prompts]", '[prompts]\ntranslate = "prompts/translate.md"'),
        encoding="utf-8",
    )
    overridden = load_project("mini")
    assert template_path(overridden, "translate") == custom
    assert load_template(overridden, "translate").startswith("CUSTOM")


def test_missing_template(project: Project, tmp_path: Path) -> None:
    text = project.paths.config_file.read_text(encoding="utf-8")
    project.paths.config_file.write_text(
        text.replace("[prompts]", '[prompts]\nrepair = "nowhere.md"'), encoding="utf-8"
    )
    with pytest.raises(FileNotFoundError, match="'repair' not found"):
        PromptBuilder(load_project("mini"))


def test_translate_prompt_contents(project: Project) -> None:
    part = load_source(project.paths).part_by_id("C01P02")
    prompt = PromptBuilder(project).translate(part, 2, 2, part.keys)
    assert "**Mini Story**" in prompt
    assert "**Part 2 of 2** (Chapter 1 · Part 2): 6 segment(s)" in prompt
    assert "Past tense. American English." in prompt
    assert "- 姉 → my sister" in prompt
    assert "Return all 6 keys" in prompt
    assert requested_keys(prompt) == part.keys
    assert "{" not in prompt.replace("{segments}", "")  # every slot filled


def test_repair_prompt_contents(project: Project) -> None:
    part = load_source(project.paths).part_by_id("C01P01")
    prompt = PromptBuilder(project).repair(part, 1, 2, ["S002", "S005"], "keys not returned")
    assert requested_keys(prompt) == ["S002", "S005"]
    assert "keys not returned" in prompt
    assert "2 segment(s)" in prompt


def test_part_header_single_segment(project: Project) -> None:
    part = load_source(project.paths).part_by_id("C01P01")
    header = part_header(part, 1, 2, {"S003": part.source_text("S003")})
    assert header.endswith("1 segment(s), 13 characters, S003")
