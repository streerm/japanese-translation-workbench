"""Command-line interface (`jtw`)."""

from __future__ import annotations

from typing import Annotated

import typer

from jtw import __version__
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
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
        ),
    ] = False,
) -> None:
    """Japanese-to-English translation workbench."""


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
