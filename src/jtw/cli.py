"""Command-line interface (`jtw`)."""

from __future__ import annotations

from typing import Annotated

import typer
from dotenv import find_dotenv, load_dotenv

from jtw import __version__
from jtw.config import ConfigError, Project, load_project
from jtw.llm.base import MissingAPIKey
from jtw.llm.registry import ProviderFactory, Registry, build_registry, default_factory
from jtw.model.store import StoreError
from jtw.mt.pipeline import translate as run_translation
from jtw.projects import ProjectExists, create_project, discover

app = typer.Typer(
    name="jtw",
    help="Japanese-to-English translation workbench.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"jtw {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
        ),
    ] = False,
) -> None:
    """Japanese-to-English translation workbench."""
    load_dotenv(find_dotenv(usecwd=True))
    ctx.ensure_object(dict)


def _registry(ctx: typer.Context, project: Project) -> Registry:
    # Tests (and offline demos) inject a provider factory through the context object.
    factory: ProviderFactory = ctx.obj.get("provider_factory", default_factory)
    return build_registry(project.config, factory)


def _project(slug: str) -> Project:
    try:
        return load_project(slug)
    except (ConfigError, ValueError) as exc:
        raise _fail(str(exc)) from None


def _fail(message: str, code: int = 1) -> typer.Exit:
    typer.secho(message, err=True, fg=typer.colors.RED)
    return typer.Exit(code)


@app.command()
def new(slug: Annotated[str, typer.Argument(help="Directory name for the new project.")]) -> None:
    """Create projects/<slug>/ from the template."""
    try:
        paths = create_project(slug)
    except (ProjectExists, ValueError) as exc:
        raise _fail(str(exc)) from None
    typer.echo(f"Created {paths.root}")
    typer.echo(f"Next: edit {paths.config_file}, then `jtw ingest {slug} <file.txt>`.")


@app.command("list")
def list_projects() -> None:
    """List projects with part counts and progress."""
    summaries = discover()
    if not summaries:
        typer.echo("No projects found. Create one with `jtw new <slug>`.")
        return
    typer.echo(f"{'slug':<20} {'parts':>5} {'segments':>8} {'final':>7}  title")
    for s in summaries:
        if s.error:
            typer.echo(f"{s.slug:<20} {'-':>5} {'-':>8} {'-':>7}  (invalid: {s.error})")
            continue
        parts = "-" if s.parts is None else str(s.parts)
        typer.echo(f"{s.slug:<20} {parts:>5} {s.segments:>8} {s.finalized_pct:>6.1f}%  {s.title}")


@app.command()
def translate(
    ctx: typer.Context,
    slug: Annotated[str, typer.Argument(help="Project slug.")],
    parts: Annotated[
        str | None,
        typer.Option(help="Comma-separated part ids, positions or ranges, e.g. 1,3-5,C02P01."),
    ] = None,
    all_parts: Annotated[bool, typer.Option("--all", help="Translate every part.")] = False,
    column: Annotated[
        list[str] | None,
        typer.Option(help="Only this MT column (repeatable). Default: every column."),
    ] = None,
    repairs: Annotated[
        int | None,
        typer.Option(min=0, help="Repair passes per part (default: limits.repair_passes)."),
    ] = None,
    overwrite: Annotated[
        bool, typer.Option(help="Re-translate cells that already hold text.")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print the prompts; call nothing.")
    ] = False,
) -> None:
    """Machine-translate parts into the project's MT columns.

    Exactly one of --parts or --all is required, so no command spends money by default.
    Re-running the same command resumes: filled cells are skipped.
    """
    if bool(parts) == all_parts:
        raise _fail("pass exactly one of --parts or --all", code=2)
    project = _project(slug)
    specs = None if all_parts else [p for p in (parts or "").split(",") if p.strip()]
    try:
        summary = run_translation(
            project,
            None if dry_run else _registry(ctx, project),
            part_specs=specs,
            columns=column,
            repairs=repairs,
            overwrite=overwrite,
            dry_run=dry_run,
            report=typer.echo,
        )
    except (StoreError, ValueError, FileNotFoundError, MissingAPIKey) as exc:
        raise _fail(str(exc)) from None

    if dry_run:
        typer.echo(f"Dry run: {len(summary.jobs)} request(s) would be sent; nothing was called.")
        return
    typer.echo(
        f"translated: {summary.translated}   skipped: {summary.skipped}   failed: {summary.failed}"
    )
    if not summary.ok:
        typer.echo("Re-run the same command to retry only what is still blank.")
        raise typer.Exit(1)
