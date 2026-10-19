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


@pytest.fixture
def worked_paths(mini_paths: ProjectPaths) -> ProjectPaths:
    """The mini project with some translation work saved in part C01P01."""
    from jtw.model import store

    loaded = store.load_part(mini_paths, "C01P01", COLUMNS)
    segs = loaded.segments
    for key, seg in segs.items():
        seg.mt["alpha"] = f"Alpha {key}."
    segs["S001"].final = "I woke at seven..."
    segs["S001"].is_finalized = True
    segs["S002"].final = "Outside, the rain fell *quietly*."
    segs["S002"].merge_with_next = True
    segs["S003"].final = '"Morning," my sister said.'
    segs["S003"].notes = "Sister or older sister?"
    segs["S003"].is_finalized = True
    segs["S004"].final = "I made **toast** and tea."
    segs["S005"].merge_with_next = True  # chain with an empty final
    segs["S006"].final = "I decided to walk to the station."
    store.save_part(mini_paths, "C01P01", segs)
    return mini_paths
