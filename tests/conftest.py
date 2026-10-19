from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from jtw.paths import PROJECTS_DIR_ENV, ProjectPaths

FIXTURES = Path(__file__).parent / "fixtures"
COLUMNS = ("alpha", "beta")


@pytest.fixture
def projects_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty projects directory, wired in through ``JTW_PROJECTS_DIR``."""
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv(PROJECTS_DIR_ENV, str(root))
    return root


@pytest.fixture
def mini_paths(projects_dir: Path) -> ProjectPaths:
    """A copy of the synthetic two-part project, with its working directories."""
    shutil.copytree(FIXTURES / "mini_project", projects_dir / "mini")
    paths = ProjectPaths(projects_dir / "mini")
    paths.ensure_dirs()
    return paths


@pytest.fixture
def columns() -> tuple[str, ...]:
    return COLUMNS
