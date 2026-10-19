"""Filesystem layout of a project.

Projects live in ``./projects/<slug>/`` by default. Set ``JTW_PROJECTS_DIR`` to keep them
somewhere else (tests point it at a temporary directory).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

PROJECTS_DIR_ENV = "JTW_PROJECTS_DIR"
TEMPLATE_SLUG = "_template"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def projects_root() -> Path:
    """The directory that holds every project."""
    override = os.environ.get(PROJECTS_DIR_ENV)
    return Path(override) if override else Path.cwd() / "projects"


def validate_slug(slug: str) -> str:
    if not SLUG_RE.match(slug):
        raise ValueError(
            f"invalid project slug {slug!r}: use lowercase letters, digits, '-' and '_', "
            "starting with a letter or digit"
        )
    return slug


@dataclass(frozen=True)
class ProjectPaths:
    """Every path a project uses, derived from its root directory."""

    root: Path

    @classmethod
    def for_slug(cls, slug: str, projects_dir: Path | None = None) -> ProjectPaths:
        base = projects_dir if projects_dir is not None else projects_root()
        return cls(base / validate_slug(slug))

    @property
    def slug(self) -> str:
        return self.root.name

    @property
    def config_file(self) -> Path:
        return self.root / "project.toml"

    @property
    def source_file(self) -> Path:
        return self.root / "source.json"

    @property
    def saves(self) -> Path:
        return self.root / "saves"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def tmp(self) -> Path:
        return self.root / "tmp"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    def latest_save(self, part_id: str) -> Path:
        return self.saves / f"{part_id}.latest.json"

    def ensure_dirs(self) -> None:
        for directory in (self.saves, self.logs, self.tmp, self.exports):
            directory.mkdir(parents=True, exist_ok=True)
