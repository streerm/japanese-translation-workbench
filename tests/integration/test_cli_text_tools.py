import json
from pathlib import Path

from typer.testing import CliRunner

from jtw.cli import app
from jtw.paths import ProjectPaths

runner = CliRunner()


def test_ingest(projects_dir: Path, tmp_path: Path) -> None:
    assert runner.invoke(app, ["new", "story"]).exit_code == 0
    source = tmp_path / "story.txt"
    source.write_text("第一章\n\n朝だ。雨だ。\n\n「おはよう」", encoding="utf-8")
    args = ["ingest", "story", str(source), "--split-on-headings"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "1 part(s), 3 segment(s)" in result.output
    data = json.loads((projects_dir / "story" / "source.json").read_text(encoding="utf-8"))
    assert data["parts"][0]["id"] == "C01P01"
    assert data["parts"][0]["chapter_title"] == "第一章"

    again = runner.invoke(app, ["ingest", "story", str(source)])
    assert again.exit_code == 1 and "--force" in again.output
    assert runner.invoke(app, ["ingest", "story", str(source), "--force"]).exit_code == 0


def test_ingest_encodings(projects_dir: Path, tmp_path: Path) -> None:
    runner.invoke(app, ["new", "sj"])
    source = tmp_path / "sj.txt"
    source.write_bytes("朝だ。".encode("shift_jis"))
    assert runner.invoke(app, ["ingest", "sj", str(source)]).exit_code == 1
    result = runner.invoke(app, ["ingest", "sj", str(source), "--encoding", "shift_jis"])
    assert result.exit_code == 0, result.output
    empty = tmp_path / "empty.txt"
    empty.write_text("第一章", encoding="utf-8")
    result = runner.invoke(app, ["ingest", "sj", str(empty), "--force", "--split-on-headings"])
    assert result.exit_code == 1 and "no segments" in result.output


def test_export_stats_search(worked_paths: ProjectPaths, tmp_path: Path) -> None:
    result = runner.invoke(app, ["export", "mini", "--parts", "1", "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "Mini_Story.C01P01.docx").exists()
    result = runner.invoke(app, ["export", "mini", "--what", "side-by-side"])
    assert result.exit_code == 0 and result.output.count(".JE_Draft.docx") == 2
    assert runner.invoke(app, ["export", "mini", "--parts", "7"]).exit_code == 1

    result = runner.invoke(app, ["stats", "mini"])
    assert result.exit_code == 0 and "C01P02" in result.output and "total" in result.output
    data = json.loads(runner.invoke(app, ["stats", "mini", "--json"]).output)
    assert data["totals"]["segments"] == 12

    result = runner.invoke(app, ["search", "mini", "雨", "--context", "0"])
    assert result.exit_code == 0
    assert "C01P01/S002" in result.output and "2 match(es)." in result.output
    result = runner.invoke(app, ["search", "mini", "alpha s004"])
    assert "[Model A]" in result.output and "1 match(es)." in result.output
    result = runner.invoke(app, ["search", "mini", "sister", "--lang", "en"])
    assert "my sister said" in result.output


def test_text_tools_without_source(projects_dir: Path) -> None:
    runner.invoke(app, ["new", "bare"])
    for args in (["stats", "bare"], ["search", "bare", "x"], ["export", "bare"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 1 and "jtw ingest" in result.output
