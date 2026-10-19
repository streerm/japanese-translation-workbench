import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from jtw.cli import app
from jtw.config import load_project
from jtw.model import store
from jtw.paths import ProjectPaths
from jtw.resources import bundled_template

runner = CliRunner()


def test_new_creates_tree_from_bundled_template(projects_dir: Path) -> None:
    result = runner.invoke(app, ["new", "my-work"])
    assert result.exit_code == 0, result.output
    root = projects_dir / "my-work"
    for sub in ("saves", "logs", "tmp", "exports"):
        assert (root / sub).is_dir()
    assert load_project("my-work").config.work.slug == "my-work"


def test_new_prefers_local_template(projects_dir: Path) -> None:
    (projects_dir / "_template").mkdir()
    shutil.copyfile(bundled_template(), projects_dir / "_template" / "project.toml")
    (projects_dir / "_template" / "notes.md").write_text("house rules", encoding="utf-8")
    assert runner.invoke(app, ["new", "w2"]).exit_code == 0
    assert (projects_dir / "w2" / "notes.md").read_text(encoding="utf-8") == "house rules"
    assert load_project("w2").config.work.slug == "w2"


def test_new_refuses_to_overwrite(projects_dir: Path) -> None:
    assert runner.invoke(app, ["new", "dup"]).exit_code == 0
    marker = projects_dir / "dup" / "project.toml"
    marker.write_text("edited", encoding="utf-8")
    result = runner.invoke(app, ["new", "dup"])
    assert result.exit_code == 1
    assert "already exists" in result.output
    assert marker.read_text(encoding="utf-8") == "edited"


def test_new_rejects_bad_slug(projects_dir: Path) -> None:
    result = runner.invoke(app, ["new", "Bad Slug"])
    assert result.exit_code == 1
    assert "invalid project slug" in result.output


def test_list_empty(projects_dir: Path) -> None:
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No projects found" in result.output


def test_list_missing_projects_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JTW_PROJECTS_DIR", str(tmp_path / "absent"))
    assert "No projects found" in runner.invoke(app, ["list"]).output


def test_list_populated(mini_paths: ProjectPaths, projects_dir: Path) -> None:
    loaded = store.load_part(mini_paths, "C01P01", ["alpha", "beta"])
    for key in ("S001", "S002", "S003"):
        loaded.segments[key].is_finalized = True
    store.save_part(mini_paths, "C01P01", loaded.segments)
    runner.invoke(app, ["new", "fresh"])
    (projects_dir / "broken").mkdir()
    (projects_dir / "broken" / "project.toml").write_text("[work]\n", encoding="utf-8")

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    lines = {line.split()[0]: line for line in result.output.splitlines()[1:]}
    assert set(lines) == {"broken", "fresh", "mini"}
    assert "25.0%" in lines["mini"] and "Mini Story" in lines["mini"]
    assert "   12 " in lines["mini"]
    assert "invalid" in lines["broken"]
    assert "Working Title" in lines["fresh"]


def test_serve_launches_streamlit(
    mini_paths: ProjectPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess
    from types import SimpleNamespace

    seen: dict[str, object] = {}

    def fake_run(command: list[str], env: dict[str, str], check: bool) -> SimpleNamespace:
        seen.update(command=command, env=env)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = runner.invoke(app, ["serve", "--project", "mini", "--port", "8600", "--no-open"])
    assert result.exit_code == 0, result.output
    command = seen["command"]
    assert isinstance(command, list)
    assert command[1:4] == ["-m", "streamlit", "run"]
    assert command[4].endswith("jtw/ui/app.py")
    assert command[command.index("--server.port") + 1] == "8600"
    assert command[command.index("--server.headless") + 1] == "true"
    assert seen["env"]["JTW_PROJECT"] == "mini"  # type: ignore[index]
    assert runner.invoke(app, ["serve", "--project", "missing"]).exit_code == 1
