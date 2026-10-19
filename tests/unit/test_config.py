import tomllib
from pathlib import Path
from typing import Any

import pytest

from jtw.config import ConfigError, load_config, load_project, parse_config
from jtw.paths import ProjectPaths
from jtw.resources import bundled_template

REPO = Path(__file__).resolve().parents[2]


def _data() -> dict[str, Any]:
    with bundled_template().open("rb") as handle:
        return tomllib.load(handle)


def test_template_loads() -> None:
    config = load_config(REPO / "projects" / "_template" / "project.toml")
    assert config.columns == ["gpt", "opus", "fable"]
    assert config.column_label("opus") == "Opus 5"
    assert config.mt.column["gpt"].provider == "openai"
    assert config.synthesis.draft.provider == "anthropic"
    assert config.limits.keep_saves == 10
    assert "固有名詞" in config.glossary
    assert "first person" in config.prompts.style_notes


def test_fixture_project_loads(mini_paths: ProjectPaths) -> None:
    project = load_project("mini")
    assert project.slug == "mini"
    assert project.config.columns == ["alpha", "beta"]
    assert project.config.limits.repair_passes == 1
    assert project.config.limits.max_tokens_part == 32000  # default


def _set(data: dict[str, Any], dotted: str, value: object) -> dict[str, Any]:
    *parents, leaf = dotted.split(".")
    node = data
    for name in parents:
        node = node[name]
    if value is _DELETE:
        del node[leaf]
    else:
        node[leaf] = value
    return data


_DELETE = object()


@pytest.mark.parametrize(
    ("dotted", "value", "expected"),
    [
        ("mt.columns", ["gpt", "opus", "fable", "extra"], "mt: mt.columns: 'extra' has no"),
        ("mt.columns", ["gpt", "opus"], "mt: mt.column.fable: defined but not listed"),
        ("mt.columns", ["gpt", "gpt", "opus", "fable"], "duplicates"),
        ("mt.columns", [], "mt.columns: List should have at least 1"),
        ("mt.column.gpt.provider", "mistral", "mt.column.gpt.provider: Input should be"),
        ("mt.column.opus.model", "", "mt.column.opus.model: String should have at least"),
        ("mt.column.opus.label", _DELETE, "mt.column.opus.label: Field required"),
        ("synthesis.draft.provider", "x", "synthesis.draft.provider"),
        ("work.title", _DELETE, "work.title: Field required"),
        ("work.source_lang", "zh", "work.source_lang"),
        ("limits.keep_saves", 0, "limits.keep_saves"),
        ("limits.surprise", 1, "limits.surprise: Extra inputs are not permitted"),
    ],
)
def test_validation_errors_name_the_path(dotted: str, value: object, expected: str) -> None:
    with pytest.raises(ConfigError) as info:
        parse_config(_set(_data(), dotted, value))
    assert expected in str(info.value)


@pytest.mark.parametrize(
    ("column", "expected"),
    [("Gpt", "must match"), ("1x", "must match"), ("final", "reserved"), ("mt", "reserved")],
)
def test_column_id_rules(column: str, expected: str) -> None:
    data = _data()
    data["mt"]["column"][column] = data["mt"]["column"].pop("gpt")
    data["mt"]["columns"][0] = column
    with pytest.raises(ConfigError, match=expected):
        parse_config(data)


def test_load_errors(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.toml")
    bad = tmp_path / "bad.toml"
    bad.write_text("[work\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(bad)


def test_slug_must_match_directory(mini_paths: ProjectPaths) -> None:
    text = mini_paths.config_file.read_text(encoding="utf-8")
    mini_paths.config_file.write_text(text.replace('"mini"', '"other"'), encoding="utf-8")
    with pytest.raises(ConfigError, match="does not match"):
        load_project("mini")
