"""Locating files that ship with the package: default prompts and the project template.

In a wheel they are bundled under ``jtw/`` (see ``force-include`` in ``pyproject.toml``); in a
source checkout they are read from the repository's ``prompts/`` and ``projects/_template/``.
"""

from __future__ import annotations

from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_DIR.parent.parent


def _first_existing(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"bundled resource not found: {candidates[-1]}")


def default_prompts_dir() -> Path:
    return _first_existing(_PACKAGE_DIR / "prompts", _REPO_ROOT / "prompts")


def bundled_template() -> Path:
    """The default ``project.toml`` template."""
    return _first_existing(
        _PACKAGE_DIR / "templates" / "project.toml",
        _REPO_ROOT / "projects" / "_template" / "project.toml",
    )
