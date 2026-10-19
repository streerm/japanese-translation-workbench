from pathlib import Path

import pytest

from jtw.paths import PROJECTS_DIR_ENV, ProjectPaths, projects_root, validate_slug


def test_projects_root_defaults_to_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(PROJECTS_DIR_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    assert projects_root() == tmp_path / "projects"


def test_projects_root_env_override(projects_dir: Path) -> None:
    assert projects_root() == projects_dir


def test_for_slug_layout(projects_dir: Path) -> None:
    paths = ProjectPaths.for_slug("my-work")
    assert paths.root == projects_dir / "my-work"
    assert paths.slug == "my-work"
    assert paths.config_file.name == "project.toml"
    assert paths.source_file.name == "source.json"
    assert paths.latest_save("C01P01") == paths.saves / "C01P01.latest.json"
    paths.ensure_dirs()
    for d in (paths.saves, paths.logs, paths.tmp, paths.exports):
        assert d.is_dir()


@pytest.mark.parametrize("slug", ["", "Bad", "-x", "a b", "../up", "_template"])
def test_invalid_slugs(slug: str) -> None:
    with pytest.raises(ValueError):
        validate_slug(slug)
