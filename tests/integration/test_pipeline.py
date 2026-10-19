from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from tests.helpers import english, requested_keys, translator
from typer.testing import CliRunner

from jtw.cli import app
from jtw.config import Project, ProjectConfig, load_project
from jtw.llm.base import MissingAPIKey, ModelRefusal, ModelResult, Provider
from jtw.llm.fake import FakeProvider
from jtw.llm.registry import build_registry
from jtw.model import store
from jtw.mt import pipeline
from jtw.mt.log import list_logs
from jtw.paths import ProjectPaths

runner = CliRunner()


@pytest.fixture
def project(mini_paths: ProjectPaths) -> Project:
    return load_project("mini")


def _factory(fake: FakeProvider) -> Callable[[str, ProjectConfig], Provider]:
    return lambda name, config: fake


def _run(project: Project, fake: FakeProvider, **kw: Any) -> pipeline.RunSummary:
    registry = build_registry(project.config, _factory(fake))
    kw.setdefault("part_specs", None)
    return pipeline.translate(project, registry, **kw)


def _mt(project: Project, part_id: str, column: str) -> dict[str, str]:
    loaded = store.load_part(project.paths, part_id, project.config.columns)
    return {k: s.mt[column] for k, s in loaded.segments.items()}


def test_happy_path_fills_every_cell(project: Project) -> None:
    fake = FakeProvider([translator("a"), translator("a"), translator("b"), translator("b")])
    summary = _run(project, fake)
    assert summary.ok and summary.translated == 24 and summary.skipped == 0
    assert [c.model for c in fake.calls] == ["fake-model-a"] * 2 + ["fake-model-b"] * 2
    assert all(c.max_tokens == 32000 and c.system for c in fake.calls)
    for part_id in ("C01P01", "C01P02"):
        assert _mt(project, part_id, "alpha") == {
            f"S00{i}": english(f"S00{i}", "a") for i in range(1, 7)
        }
        assert all(_mt(project, part_id, "beta").values())


def test_repair_requests_exactly_the_missing_keys(project: Project) -> None:
    fake = FakeProvider([translator(drop=("S002", "S005")), translator()])
    summary = _run(project, fake, part_specs=["1"], columns=["alpha"])
    assert summary.ok
    assert len(fake.calls) == 2
    repair_prompt = fake.calls[1].prompt
    assert requested_keys(repair_prompt) == ["S002", "S005"]
    assert "keys merged with a neighbouring segment: S002, S005" in repair_prompt
    assert all(_mt(project, "C01P01", "alpha").values())
    assert summary.outcomes[0].attempts == 2


def test_accepted_keys_are_saved_before_the_repair(project: Project) -> None:
    seen: list[dict[str, str]] = []

    def check_then_answer(call: Any) -> str:
        seen.append(_mt(project, "C01P01", "alpha"))
        return translator()(call)

    fake = FakeProvider([translator(drop=("S006",)), check_then_answer])
    _run(project, fake, part_specs=["C01P01"], columns=["alpha"])
    assert seen[0]["S001"] and not seen[0]["S006"]


def test_repairs_exhausted_leave_cells_blank(project: Project) -> None:
    fake = FakeProvider([translator(drop=("S006",)), "[S006]\n雨の音だけが聞こえていた。"])
    summary = _run(project, fake, part_specs=["C01P02"], columns=["alpha"])
    assert not summary.ok and summary.failed == 1 and summary.translated == 5
    outcome = summary.outcomes[0]
    assert outcome.outstanding == ["S006"]
    assert "still in Japanese: S006" in outcome.problems
    assert _mt(project, "C01P02", "alpha")["S006"] == ""


def test_resume_skips_filled_cells(project: Project) -> None:
    first = FakeProvider([translator(drop=("S003",)), translator(drop=("S003",))])
    _run(project, first, columns=["alpha"], repairs=0)
    fake = FakeProvider([translator(), translator()])
    summary = _run(project, fake, columns=["alpha"])
    assert [requested_keys(c.prompt) for c in fake.calls] == [["S003"], ["S003"]]
    assert summary.skipped == 10 and summary.translated == 2


def test_overwrite_retranslates(project: Project) -> None:
    _run(project, FakeProvider([translator("a")]), part_specs=["1"], columns=["alpha"])
    summary = _run(
        project,
        FakeProvider([translator("z")]),
        part_specs=["1"],
        columns=["alpha"],
        overwrite=True,
    )
    assert summary.translated == 6
    assert _mt(project, "C01P01", "alpha")["S001"] == english("S001", "z")


def test_dry_run_calls_nothing_and_writes_nothing(project: Project) -> None:
    printed: list[str] = []
    summary = pipeline.translate(
        project, None, part_specs=None, dry_run=True, report=printed.append
    )
    assert summary.dry_run and len(summary.jobs) == 4
    assert sum("## The segments to translate" in p for p in printed) == 4
    assert list(project.paths.saves.iterdir()) == []
    assert list_logs(project.paths) == []
    with pytest.raises(ValueError, match="registry is required"):
        pipeline.translate(project, None, part_specs=None)


def test_model_mismatch_is_discarded_and_logged(project: Project) -> None:
    fake = FakeProvider([translator()], served_model="fake-model-imposter")
    summary = _run(project, fake, part_specs=["1"], columns=["alpha"])
    assert not summary.ok
    assert "fake-model-imposter" in (summary.outcomes[0].error or "")
    assert not any(_mt(project, "C01P01", "alpha").values())
    (log_path,) = list_logs(project.paths)
    record = json.loads(log_path.read_text(encoding="utf-8"))
    assert record["model_returned"] == "fake-model-imposter"
    assert record["response"].startswith("[S001]")
    assert "discarded" not in record["error"] and "imposter" in record["error"]


def test_log_shape(project: Project) -> None:
    _run(
        project,
        FakeProvider([translator(drop=("S001",)), translator()]),
        part_specs=["1"],
        columns=["beta"],
    )
    logs = list_logs(project.paths, "C01P01")
    assert [p.name.split("_")[2] for p in logs] == ["1", "2"]
    first = json.loads(logs[0].read_text(encoding="utf-8"))
    assert {
        "timestamp",
        "part_id",
        "column",
        "provider",
        "model_requested",
        "model_returned",
        "attempt",
        "prompt",
        "system",
        "response",
        "usage",
        "stop_reason",
        "problems",
        "rejected",
        "accepted_keys",
        "error",
    } == set(first)
    assert first["part_id"] == "C01P01" and first["column"] == "beta"
    assert first["provider"] == "fake" and first["model_requested"] == "fake-model-b"
    assert first["rejected"] == {"missing": ["S001"]}
    assert first["accepted_keys"] == ["S002", "S003", "S004", "S005", "S006"]
    assert set(first["usage"]) == {"input_tokens", "output_tokens"}


def test_truncation_is_noted(project: Project) -> None:
    cut = ModelResult("[S001]\nA.", "fake-model-a", stop_reason="max_tokens")
    summary = _run(project, FakeProvider([cut]), part_specs=["1"], columns=["alpha"], repairs=0)
    assert "cut off (max_tokens)" in summary.outcomes[0].problems


def test_provider_errors_fail_only_their_job(project: Project) -> None:
    fake = FakeProvider([ModelRefusal("declined"), translator()])
    summary = _run(project, fake, columns=["alpha"], part_specs=["1", "2"])
    assert [o.error for o in summary.outcomes] == ["declined", None]
    summary = _run(project, FakeProvider([RuntimeError("socket")]), columns=["alpha"])
    assert summary.outcomes[0].error == "RuntimeError: socket"


def test_missing_key_is_fatal(project: Project) -> None:
    with pytest.raises(MissingAPIKey):
        _run(project, FakeProvider([MissingAPIKey("ANTHROPIC_API_KEY")]))


def test_bad_selection(project: Project) -> None:
    with pytest.raises(ValueError, match="unknown column"):
        _run(project, FakeProvider(), columns=["gamma"])
    with pytest.raises(ValueError, match="no parts selected"):
        _run(project, FakeProvider(), part_specs=[])


# --- CLI --------------------------------------------------------------------


def _invoke(args: list[str], fake: FakeProvider | None = None) -> Any:
    obj = {"provider_factory": _factory(fake)} if fake else {}
    return runner.invoke(app, args, obj=obj)


def test_cli_requires_parts_or_all(project: Project) -> None:
    for args in (["translate", "mini"], ["translate", "mini", "--all", "--parts", "1"]):
        result = _invoke(args)
        assert result.exit_code == 2
        assert "exactly one of --parts or --all" in result.output


def test_cli_translate_success(project: Project) -> None:
    fake = FakeProvider([translator(), translator()])
    result = _invoke(["translate", "mini", "--parts", "1-2", "--column", "alpha"], fake)
    assert result.exit_code == 0, result.output
    assert "translated: 12   skipped: 0   failed: 0" in result.output


def test_cli_translate_failure_exit_code(project: Project) -> None:
    fake = FakeProvider([translator(drop=("S001",))])
    result = _invoke(
        ["translate", "mini", "--parts", "1", "--column", "beta", "--repairs", "0"], fake
    )
    assert result.exit_code == 1
    assert "failed: 1" in result.output
    assert "Re-run the same command" in result.output
    assert "keys not returned at all: S001" in result.output


def test_cli_dry_run(project: Project) -> None:
    fake = FakeProvider()
    result = _invoke(["translate", "mini", "--all", "--dry-run"], fake)
    assert result.exit_code == 0
    assert "4 request(s) would be sent" in result.output
    assert fake.calls == []


def test_cli_errors(project: Project, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _invoke(["translate", "nope", "--all"]).exit_code == 1
    result = _invoke(["translate", "mini", "--parts", "9"])
    assert result.exit_code == 1 and "out of range" in result.output
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = _invoke(["translate", "mini", "--parts", "1", "--column", "alpha"])
    assert result.exit_code == 1 and "ANTHROPIC_API_KEY is not set" in result.output
