"""Creating and surveying projects."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from jtw.config import ConfigError, load_project
from jtw.model.store import StoreError, load_part, load_source
from jtw.paths import TEMPLATE_SLUG, ProjectPaths, projects_root, validate_slug
from jtw.resources import bundled_template

_SLUG_LINE_RE = re.compile(r'^(slug\s*=\s*)"[^"]*"', re.MULTILINE)


class ProjectExists(FileExistsError):
    pass


def create_project(slug: str, projects_dir: Path | None = None) -> ProjectPaths:
    """Copy the template into ``projects/<slug>/`` and create the working directories.

    The template is ``projects/_template/`` if the projects directory has one, otherwise the
    copy bundled with the package. Refuses to touch an existing directory.
    """
    base = projects_dir if projects_dir is not None else projects_root()
    paths = ProjectPaths(base / validate_slug(slug))
    if paths.root.exists():
        raise ProjectExists(f"{paths.root} already exists")

    local_template = base / TEMPLATE_SLUG
    if local_template.is_dir():
        shutil.copytree(local_template, paths.root)
    else:
        paths.root.mkdir(parents=True)
        shutil.copyfile(bundled_template(), paths.config_file)

    text = paths.config_file.read_text(encoding="utf-8")
    paths.config_file.write_text(_SLUG_LINE_RE.sub(rf'\1"{slug}"', text, count=1), "utf-8")
    paths.ensure_dirs()
    return paths


@dataclass(frozen=True)
class ProjectSummary:
    slug: str
    title: str | None
    parts: int | None
    segments: int
    finalized: int
    error: str | None = None

    @property
    def finalized_pct(self) -> float:
        return 100.0 * self.finalized / self.segments if self.segments else 0.0


def discover(projects_dir: Path | None = None) -> list[ProjectSummary]:
    """Every project under the projects directory, with progress figures."""
    base = projects_dir if projects_dir is not None else projects_root()
    if not base.is_dir():
        return []
    candidates = sorted(d for d in base.iterdir() if d.is_dir() and (d / "project.toml").exists())
    return [_summarise(d.name, base) for d in candidates if not d.name.startswith(("_", "."))]


def _summarise(slug: str, base: Path) -> ProjectSummary:
    try:
        project = load_project(slug, base)
    except (ConfigError, ValueError) as exc:
        return ProjectSummary(slug, None, None, 0, 0, error=str(exc).splitlines()[0])
    try:
        structure = load_source(project.paths)
    except StoreError:
        return ProjectSummary(slug, project.config.work.title, None, 0, 0)
    segments = finalized = 0
    for part in structure.parts:
        loaded = load_part(project.paths, part.id, project.config.columns, structure)
        segments += len(loaded.segments)
        finalized += loaded.finalized_count
    return ProjectSummary(
        slug, project.config.work.title, len(structure.parts), segments, finalized
    )
