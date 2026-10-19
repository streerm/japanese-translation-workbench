"""Command-line interface (`jtw`)."""

from __future__ import annotations

from typing import Annotated

import typer

from jtw import __version__

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
