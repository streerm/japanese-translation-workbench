"""Per-project configuration, read from ``projects/<slug>/project.toml``.

Everything that differs between works lives here: titles and names, which models fill which MT
columns, synthesis models, style notes, glossary and limits. Validation errors name the TOML
path of the offending value (``mt.column.gpt.provider: ...``).
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from jtw.model.segment import RESERVED_FIELDS
from jtw.paths import ProjectPaths

Provider = Literal["anthropic", "openai"]
COLUMN_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class ConfigError(ValueError):
    """``project.toml`` is missing or invalid."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WorkConfig(_Strict):
    slug: str = Field(min_length=1)
    title: str = Field(min_length=1)
    title_source: str = ""
    author: str = ""
    translator: str = ""
    source_lang: Literal["ja"] = "ja"
    target_lang: Literal["en"] = "en"


class ModelRef(_Strict):
    provider: Provider
    model: str = Field(min_length=1)


class ColumnConfig(ModelRef):
    label: str = Field(min_length=1)


class MTConfig(_Strict):
    columns: list[str] = Field(min_length=1)
    column: dict[str, ColumnConfig]

    @model_validator(mode="after")
    def _check_columns(self) -> Self:
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("mt.columns contains duplicates")
        for column_id in self.columns:
            if not COLUMN_ID_RE.match(column_id):
                raise ValueError(f"mt.columns: {column_id!r} must match [a-z][a-z0-9_]*")
            if column_id in RESERVED_FIELDS:
                raise ValueError(f"mt.columns: {column_id!r} is a reserved segment field name")
            if column_id not in self.column:
                raise ValueError(f"mt.columns: {column_id!r} has no [mt.column.{column_id}] table")
        for column_id in self.column:
            if column_id not in self.columns:
                raise ValueError(f"mt.column.{column_id}: defined but not listed in mt.columns")
        return self


class SynthesisConfig(_Strict):
    draft: ModelRef
    deep_dive: ModelRef


class PromptsConfig(_Strict):
    translate: str | None = None
    repair: str | None = None
    draft: str | None = None
    deep_dive: str | None = None
    clipboard: str | None = None
    style_notes: str = ""


class LimitsConfig(_Strict):
    max_tokens_part: int = Field(default=32000, gt=0)
    max_tokens_default: int = Field(default=16000, gt=0)
    request_timeout_s: float = Field(default=1800, gt=0)
    repair_passes: int = Field(default=2, ge=0)
    keep_saves: int = Field(default=10, ge=1)


class ProjectConfig(_Strict):
    work: WorkConfig
    mt: MTConfig
    synthesis: SynthesisConfig
    prompts: PromptsConfig = PromptsConfig()
    glossary: dict[str, str] = {}
    limits: LimitsConfig = LimitsConfig()

    @property
    def columns(self) -> list[str]:
        return list(self.mt.columns)

    def column_label(self, column_id: str) -> str:
        return self.mt.column[column_id].label


@dataclass(frozen=True)
class Project:
    """A loaded project: where it lives and how it is configured."""

    paths: ProjectPaths
    config: ProjectConfig

    @property
    def slug(self) -> str:
        return self.paths.slug


def parse_config(data: dict[str, object], origin: str = "project.toml") -> ProjectConfig:
    try:
        return ProjectConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_describe(exc, origin)) from None


def load_config(path: Path) -> ProjectConfig:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        raise ConfigError(f"{path} not found") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: invalid TOML ({exc})") from None
    return parse_config(data, origin=str(path))


def load_project(slug: str, projects_dir: Path | None = None) -> Project:
    paths = ProjectPaths.for_slug(slug, projects_dir)
    config = load_config(paths.config_file)
    if config.work.slug != paths.slug:
        raise ConfigError(
            f"{paths.config_file}: work.slug {config.work.slug!r} does not match "
            f"the directory name {paths.slug!r}"
        )
    return Project(paths=paths, config=config)


def _describe(exc: ValidationError, origin: str) -> str:
    lines = [f"{origin}: {exc.error_count()} problem(s)"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        message = error["msg"].removeprefix("Value error, ")
        lines.append(f"  {location}: {message}" if location else f"  {message}")
    return "\n".join(lines)
