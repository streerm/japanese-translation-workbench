"""The bulk MT pipeline: every selected part, through every selected column, with repair.

For each (part, column) the pipeline sends the part's still-blank segments in one request,
parses the reply with :mod:`jtw.mt.protocol`, saves whatever was accepted straight away, then
re-requests only the rejected segments (``repair_passes`` times). Cells that already hold text
are skipped, so re-running the same command resumes an interrupted or partly failed run.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from jtw.config import Project
from jtw.llm.base import LLMError, MissingAPIKey, ModelMismatch, ModelResult
from jtw.llm.registry import Registry, Route
from jtw.model import store
from jtw.model.part import Part, Structure
from jtw.model.store import LoadedPart
from jtw.mt.log import RequestLog, write_log
from jtw.mt.prompts import SYSTEM_PROMPT, PromptBuilder
from jtw.mt.protocol import ParseProblems, parse_response

Reporter = Callable[[str], None]


def _silent(_: str) -> None:
    return None


@dataclass(frozen=True)
class Job:
    """One request unit: the pending segments of one part for one column."""

    part: Part
    position: int  #: 1-based position of the part in the work
    column: str
    keys: tuple[str, ...]


@dataclass
class JobOutcome:
    job: Job
    accepted: dict[str, str] = field(default_factory=dict)
    problems: str = ""
    error: str | None = None
    attempts: int = 0

    @property
    def outstanding(self) -> list[str]:
        return [k for k in self.job.keys if k not in self.accepted]

    @property
    def ok(self) -> bool:
        return self.error is None and not self.outstanding


@dataclass
class RunSummary:
    jobs: list[Job] = field(default_factory=list)
    outcomes: list[JobOutcome] = field(default_factory=list)
    skipped: int = 0  #: segment cells already filled
    dry_run: bool = False

    @property
    def translated(self) -> int:
        return sum(len(o.accepted) for o in self.outcomes)

    @property
    def failed(self) -> int:
        return sum(len(o.outstanding) for o in self.outcomes)

    @property
    def ok(self) -> bool:
        return self.failed == 0


def build_jobs(
    structure: Structure,
    parts: Sequence[Part],
    columns: Sequence[str],
    loaded: Mapping[str, LoadedPart],
    *,
    overwrite: bool = False,
) -> tuple[list[Job], int]:
    """Jobs for every (part, column) with blank cells. Returns ``(jobs, skipped_cells)``.

    Jobs are ordered column by column, so one model works through the whole selection before
    the next starts.
    """
    positions = {p.id: i for i, p in enumerate(structure.parts, start=1)}
    jobs: list[Job] = []
    skipped = 0
    for column in columns:
        for part in parts:
            segments = loaded[part.id].segments
            pending = tuple(
                key
                for key in part.keys
                if overwrite or not segments[key].mt.get(column, "").strip()
            )
            skipped += len(part.keys) - len(pending)
            if pending:
                jobs.append(Job(part, positions[part.id], column, pending))
    return jobs, skipped


def _apply(project: Project, structure: Structure, job: Job, accepted: Mapping[str, str]) -> None:
    """Write accepted translations into the part's save, re-reading it first so edits made in
    the workbench while the run was going are not overwritten."""
    part = store.load_part(project.paths, job.part.id, project.config.columns, structure)
    for key, text in accepted.items():
        part.segments[key].mt[job.column] = text
    store.save_part(
        project.paths,
        job.part.id,
        part.segments,
        note=f"translate {job.column}",
        keep=project.config.limits.keep_saves,
    )


def translate_part(
    project: Project,
    structure: Structure,
    job: Job,
    route: Route,
    builder: PromptBuilder,
    *,
    repairs: int,
    report: Reporter = _silent,
) -> JobOutcome:
    """Translate one job, repairing what comes back wrong. Accepted keys are saved at once."""
    total = len(structure.parts)
    outcome = JobOutcome(job)
    outstanding = list(job.keys)
    prompt = builder.translate(job.part, job.position, total, outstanding)
    max_tokens = project.config.limits.max_tokens_part

    for attempt in range(1, repairs + 2):
        outcome.attempts = attempt
        log = RequestLog(
            part_id=job.part.id,
            column=job.column,
            provider=route.provider.name,
            model_requested=route.model,
            attempt=attempt,
            prompt=prompt,
            system=SYSTEM_PROMPT,
        )
        try:
            result = route.complete(prompt, system=SYSTEM_PROMPT, max_tokens=max_tokens)
        except ModelMismatch as exc:
            if exc.result is not None:
                _record_result(log, exc.result)
            log.error = str(exc)
            write_log(project.paths, log)
            outcome.error = f"{exc}; response discarded"
            return outcome

        _record_result(log, result)
        parsed = parse_response(result.text, outstanding)
        if result.truncated:
            parsed.problems.notes.append(f"the response was cut off ({result.stop_reason})")
        _record_parse(log, parsed.problems, list(parsed.translations))
        write_log(project.paths, log)

        if parsed.translations:
            _apply(project, structure, job, parsed.translations)
            outcome.accepted.update(parsed.translations)
        outstanding = [k for k in outstanding if k not in outcome.accepted]
        outcome.problems = parsed.problems.describe()
        if not outstanding:
            outcome.problems = ""
            return outcome
        if attempt <= repairs:
            report(f"  repair pass {attempt}: {len(outstanding)} segment(s) outstanding")
            for line in outcome.problems.splitlines():
                report(f"    - {line}")
            prompt = builder.repair(job.part, job.position, total, outstanding, outcome.problems)
    return outcome


def _record_result(log: RequestLog, result: ModelResult) -> None:
    log.model_returned = result.model
    log.response = result.text
    log.stop_reason = result.stop_reason
    log.usage = {
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
    }


def _record_parse(log: RequestLog, problems: ParseProblems, accepted: list[str]) -> None:
    log.problems = problems.describe().splitlines()
    log.rejected = problems.as_dict()
    log.accepted_keys = accepted


def translate(
    project: Project,
    registry: Registry | None,
    *,
    part_specs: Sequence[str] | None,
    columns: Sequence[str] | None = None,
    repairs: int | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
    report: Reporter = _silent,
) -> RunSummary:
    """Run the pipeline. ``part_specs=None`` means every part.

    In a dry run nothing is called and nothing is written: each prompt is passed to
    ``report`` instead, and ``registry`` may be ``None``.

    Raises :class:`MissingAPIKey` (fatal for the whole run); any other provider error fails
    only the job it happened in.
    """
    config = project.config
    structure = store.load_source(project.paths)
    parts = list(structure.parts) if part_specs is None else structure.select(part_specs)
    if not parts:
        raise ValueError("no parts selected")
    chosen = list(columns) if columns else config.columns
    unknown = [c for c in chosen if c not in config.columns]
    if unknown:
        raise ValueError(f"unknown column(s): {', '.join(unknown)}")
    repairs = config.limits.repair_passes if repairs is None else repairs

    loaded = {p.id: store.load_part(project.paths, p.id, config.columns, structure) for p in parts}
    jobs, skipped = build_jobs(structure, parts, chosen, loaded, overwrite=overwrite)
    summary = RunSummary(jobs=jobs, skipped=skipped, dry_run=dry_run)
    builder = PromptBuilder(project)

    if dry_run:
        for job in jobs:
            report(f"=== {job.part.id} · {job.column} · {len(job.keys)} segment(s) ===")
            report(builder.translate(job.part, job.position, len(structure.parts), job.keys))
        return summary
    if registry is None:
        raise ValueError("a registry is required unless dry_run is set")

    for job in jobs:
        route = registry.column(job.column)
        report(
            f"{job.part.id} · {job.column} ({route.provider.name}:{route.model}) · "
            f"{len(job.keys)} segment(s)"
        )
        try:
            outcome = translate_part(
                project, structure, job, route, builder, repairs=repairs, report=report
            )
        except MissingAPIKey:
            raise
        except LLMError as exc:
            outcome = JobOutcome(job, error=str(exc), attempts=1)
        except Exception as exc:  # one bad request must not halt a long run
            outcome = JobOutcome(job, error=f"{type(exc).__name__}: {exc}", attempts=1)
        summary.outcomes.append(outcome)
        _report_outcome(outcome, report)
    return summary


def _report_outcome(outcome: JobOutcome, report: Reporter) -> None:
    if outcome.ok:
        report(f"  ok: {len(outcome.accepted)} segment(s)")
        return
    if outcome.error:
        report(f"  failed: {outcome.error}")
    else:
        report(
            f"  incomplete: {len(outcome.outstanding)} segment(s) still blank after "
            f"{outcome.attempts} attempt(s)"
        )
        for line in outcome.problems.splitlines():
            report(f"    - {line}")
