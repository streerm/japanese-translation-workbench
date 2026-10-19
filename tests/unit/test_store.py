import json
import os
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from jtw.model import store
from jtw.model.segment import Segment
from jtw.paths import ProjectPaths

COLUMNS = ("alpha", "beta")


def _clock(start: datetime = datetime(2026, 1, 2, 3, 4, 5)) -> Iterator[datetime]:
    t = start
    while True:
        yield t
        t += timedelta(seconds=1)


def test_load_source(mini_paths: ProjectPaths) -> None:
    structure = store.load_source(mini_paths)
    assert structure.ids == ["C01P01", "C01P02"]
    assert len(structure.part_by_id("C01P01").segments) == 6
    assert structure.chapters()[0].title == "朝"


def test_first_load_is_blank(mini_paths: ProjectPaths) -> None:
    loaded = store.load_part(mini_paths, "C01P01", COLUMNS)
    assert loaded.keys == [f"S00{i}" for i in range(1, 7)]
    first = loaded.segments["S001"]
    assert first.source == "朝の七時に目が覚めた。"
    assert first.mt == {"alpha": "", "beta": ""}
    assert loaded.orphans == []
    assert loaded.finalized_count == 0


def test_save_load_round_trip(mini_paths: ProjectPaths) -> None:
    loaded = store.load_part(mini_paths, "C01P01", COLUMNS)
    loaded.segments["S002"].mt["alpha"] = "It was raining."
    loaded.segments["S002"].final = "Outside, rain fell quietly."
    loaded.segments["S002"].is_finalized = True
    path = store.save_part(mini_paths, "C01P01", loaded.segments, note="test")

    assert path.exists()
    data = json.loads(mini_paths.latest_save("C01P01").read_text(encoding="utf-8"))
    assert data["schema"] == 1
    assert data["metadata"]["part_id"] == "C01P01"
    assert data["metadata"]["note"] == "test"
    assert data["metadata"]["finalized_segments"] == 1
    assert data["metadata"]["total_segments"] == 6

    again = store.load_part(mini_paths, "C01P01", COLUMNS)
    assert again.segments == loaded.segments


def _write_save(paths: ProjectPaths, part_id: str, segments: dict[str, Any]) -> None:
    paths.latest_save(part_id).write_text(
        json.dumps({"schema": 1, "metadata": {}, "segments": segments}), encoding="utf-8"
    )


def test_save_wins_and_blank_fill(mini_paths: ProjectPaths) -> None:
    _write_save(
        mini_paths,
        "C01P01",
        {
            "S001": {"source": "訂正した文。", "final": "Fixed.", "is_finalized": True},
            "S002": {"final": "No source recorded."},
        },
    )
    loaded = store.load_part(mini_paths, "C01P01", COLUMNS)
    assert loaded.segments["S001"].source == "訂正した文。"  # save wins over source
    assert loaded.segments["S001"].is_finalized
    assert loaded.segments["S002"].source == "窓の外では雨が静かに降っていた。"
    assert loaded.segments["S002"].final == "No source recorded."
    assert loaded.segments["S006"] == Segment(
        key="S006", source="今日は駅まで歩くことにした。", mt={"alpha": "", "beta": ""}
    )


def test_orphans_are_kept_and_reported(mini_paths: ProjectPaths) -> None:
    _write_save(mini_paths, "C01P01", {"S099": {"source": "消えた文。", "final": "Gone."}})
    loaded = store.load_part(mini_paths, "C01P01", COLUMNS)
    assert loaded.orphans == ["S099"]
    assert loaded.keys[-1] == "S099"
    assert loaded.segments["S099"].final == "Gone."
    store.save_part(mini_paths, "C01P01", loaded.segments)
    assert "S099" in json.loads(mini_paths.latest_save("C01P01").read_text())["segments"]


def test_rotation_keeps_exactly_n(mini_paths: ProjectPaths) -> None:
    loaded = store.load_part(mini_paths, "C01P02", COLUMNS)
    clock = _clock()
    written = [
        store.save_part(mini_paths, "C01P02", loaded.segments, keep=3, now=lambda: next(clock))
        for _ in range(5)
    ]
    saves = store.list_saves(mini_paths, "C01P02")
    assert saves == list(reversed(written[-3:]))
    assert mini_paths.latest_save("C01P02").exists()
    assert store.list_saves(mini_paths, "C01P01") == []


def test_same_second_saves_do_not_collide(mini_paths: ProjectPaths) -> None:
    loaded = store.load_part(mini_paths, "C01P01", COLUMNS)
    fixed = datetime(2026, 1, 1)
    a = store.save_part(mini_paths, "C01P01", loaded.segments, now=lambda: fixed)
    b = store.save_part(mini_paths, "C01P01", loaded.segments, now=lambda: fixed)
    assert a != b
    assert store.list_saves(mini_paths, "C01P01") == [b, a]


def test_atomic_write_leaves_nothing_on_failure(
    mini_paths: ProjectPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = store.load_part(mini_paths, "C01P01", COLUMNS)
    store.save_part(mini_paths, "C01P01", loaded.segments, note="good")
    before = sorted(p.name for p in mini_paths.saves.iterdir())

    def boom(src: str, dst: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    loaded.segments["S001"].final = "never written"
    with pytest.raises(OSError):
        store.save_part(mini_paths, "C01P01", loaded.segments, note="bad")

    assert sorted(p.name for p in mini_paths.saves.iterdir()) == before
    latest = json.loads(mini_paths.latest_save("C01P01").read_text())
    assert latest["metadata"]["note"] == "good"


def test_source_payload_round_trip(mini_paths: ProjectPaths) -> None:
    structure = store.load_source(mini_paths)
    assert store.parse_source(store.source_payload(structure)) == structure


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "top level"),
        ({"schema": 2, "parts": []}, "schema"),
        ({"schema": 1}, "'parts'"),
        ({"schema": 1, "parts": ["x"]}, "must be an object"),
        ({"schema": 1, "parts": [{"id": "a/b", "segments": []}]}, "filename-safe"),
        ({"schema": 1, "parts": [{"id": "A"}]}, "segments must be a list"),
        ({"schema": 1, "parts": [{"id": "A", "segments": [1]}]}, "must be an object"),
        ({"schema": 1, "parts": [{"id": "A", "segments": [{"key": "x"}]}]}, "look like"),
        (
            {"schema": 1, "parts": [{"id": "A", "segments": [{"key": "S001", "source": 1}]}]},
            "must be a string",
        ),
        (
            {
                "schema": 1,
                "parts": [{"id": "A", "segments": [{"key": "S001", "source": "a"}] * 2}],
            },
            "duplicate segment",
        ),
        (
            {
                "schema": 1,
                "parts": [
                    {
                        "id": "A",
                        "segments": [
                            {"key": "S002", "source": "a"},
                            {"key": "S001", "source": "b"},
                        ],
                    }
                ],
            },
            "not in order",
        ),
        (
            {"schema": 1, "parts": [{"id": "A", "segments": []}, {"id": "A", "segments": []}]},
            "duplicate part",
        ),
    ],
)
def test_parse_source_rejects(payload: object, message: str) -> None:
    with pytest.raises(store.StoreError, match=message):
        store.parse_source(payload)


def test_missing_and_bad_files(mini_paths: ProjectPaths) -> None:
    mini_paths.latest_save("C01P01").write_text("{nope", encoding="utf-8")
    with pytest.raises(store.StoreError, match="invalid JSON"):
        store.load_part(mini_paths, "C01P01", COLUMNS)
    mini_paths.latest_save("C01P01").write_text("{}", encoding="utf-8")
    with pytest.raises(store.StoreError, match="segments"):
        store.read_save(mini_paths, "C01P01")
    mini_paths.source_file.write_text("{nope", encoding="utf-8")
    with pytest.raises(store.StoreError, match="invalid JSON"):
        store.load_source(mini_paths)
    mini_paths.source_file.unlink()
    with pytest.raises(store.StoreError, match="jtw ingest"):
        store.load_source(mini_paths)
    assert store.list_saves(ProjectPaths(mini_paths.root / "none"), "C01P01") == []
