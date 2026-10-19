"""Command-line interface (`jtw`)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

import typer
from dotenv import find_dotenv, load_dotenv

from jtw import __version__
from jtw.config import ConfigError, Project, load_project
from jtw.export.docx import ExportKind, export_part
from jtw.export.stats import format_table, project_stats
from jtw.llm.base import MissingAPIKey
from jtw.llm.registry import ProviderFactory, Registry, build_registry, default_factory
from jtw.model import store
from jtw.model.store import StoreError
from jtw.mt.pipeline import translate as run_translation
from jtw.projects import ProjectExists, create_project, discover
from jtw.search import guess_lang, highlight_spans
from jtw.search import search as run_search
from jtw.text.segmenter import DEFAULT_PART_CHARS, build_structure

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


@app.command()
def ingest(
    slug: Annotated[str, typer.Argument(help="Project slug.")],
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Plain-text source.")],
    part_chars: Annotated[
        int, typer.Option(min=100, help="Target Japanese characters per part.")
    ] = DEFAULT_PART_CHARS,
    split_on_headings: Annotated[
        bool, typer.Option(help="Start a new chapter at each heading line (第一章, 序章, ...).")
    ] = False,
    encoding: Annotated[str, typer.Option(help="Text encoding, e.g. utf-8 or shift_jis.")] = (
        "utf-8"
    ),
    force: Annotated[bool, typer.Option(help="Overwrite an existing source.json.")] = False,
) -> None:
    """Split a plain-text file into parts and segments and write source.json."""
    project = _project(slug)
    target = project.paths.source_file
    if target.exists() and not force:
        raise _fail(f"{target} already exists; pass --force to replace it")
    try:
        text = file.read_text(encoding="utf-8-sig" if encoding.lower() == "utf-8" else encoding)
    except (UnicodeDecodeError, LookupError) as exc:
        raise _fail(f"could not read {file} as {encoding}: {exc}") from None
    try:
        structure = build_structure(
            text, part_chars=part_chars, split_on_headings=split_on_headings
        )
    except ValueError as exc:
        raise _fail(str(exc)) from None
    payload = store.source_payload(structure)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    segments = sum(len(p.segments) for p in structure.parts)
    typer.echo(f"Wrote {target}: {len(structure.parts)} part(s), {segments} segment(s).")


def _selected_parts(project: Project, parts: str | None) -> list[str]:
    structure = store.load_source(project.paths)
    if not parts:
        return structure.ids
    return [p.id for p in structure.select(parts.split(","))]


@app.command()
def export(
    slug: Annotated[str, typer.Argument(help="Project slug.")],
    what: Annotated[ExportKind, typer.Option(help="What to export.")] = ExportKind.FINAL,
    parts: Annotated[str | None, typer.Option(help="Parts to export (default: all).")] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Directory (default: exports/).")
    ] = None,
) -> None:
    """Export parts to Word: final English, side-by-side J-E draft, or the source."""
    project = _project(slug)
    try:
        part_ids = _selected_parts(project, parts)
        structure = store.load_source(project.paths)
        for part_id in part_ids:
            loaded = store.load_part(project.paths, part_id, project.config.columns, structure)
            typer.echo(str(export_part(project, loaded, what, output)))
    except (StoreError, ValueError) as exc:
        raise _fail(str(exc)) from None


@app.command()
def stats(
    slug: Annotated[str, typer.Argument(help="Project slug.")],
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """Character counts and translation progress per part."""
    project = _project(slug)
    try:
        result = project_stats(project)
    except StoreError as exc:
        raise _fail(str(exc)) from None
    if as_json:
        typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        typer.echo(format_table(result))


def _styled(text: str, query: str) -> str:
    return "".join(
        typer.style(piece, fg=typer.colors.YELLOW, bold=True) if hit else piece
        for piece, hit in highlight_spans(text, query)
    )


@app.command()
def search(
    slug: Annotated[str, typer.Argument(help="Project slug.")],
    query: Annotated[str, typer.Argument(help="Text to find (Japanese or English).")],
    lang: Annotated[
        Literal["ja", "en", "both"] | None,
        typer.Option(help="Search the source (ja), translations (en) or both. Default: guess."),
    ] = None,
    context: Annotated[int, typer.Option(min=0, help="Neighbouring segments to show.")] = 1,
) -> None:
    """Search the source and translations of every part."""
    project = _project(slug)
    try:
        hits = run_search(project, query, lang=lang or guess_lang(query), context=context)
    except StoreError as exc:
        raise _fail(str(exc)) from None
    for hit in hits:
        typer.secho(f"{hit.ref}  ({hit.part_label}; in {', '.join(hit.fields)})", bold=True)
        for neighbour in hit.before:
            typer.echo(f"    {neighbour.key}  {neighbour.source}")
        seg = hit.segment
        typer.echo(f"  > {seg.key}  {_styled(seg.source, query)}")
        if seg.final:
            typer.echo(f"           {_styled(seg.final, query)}")
        for column in hit.fields:
            if column in seg.mt:
                label = project.config.column_label(column)
                typer.echo(f"           [{label}] {_styled(seg.mt[column], query)}")
        for neighbour in hit.after:
            typer.echo(f"    {neighbour.key}  {neighbour.source}")
        typer.echo("")
    typer.echo(f"{len(hits)} match(es).")
