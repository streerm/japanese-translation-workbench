"""One JSON record per MT request, under ``<project>/logs/``, for auditing a run afterwards."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from jtw.paths import ProjectPaths


@dataclass
class RequestLog:
    part_id: str
    column: str
    provider: str
    model_requested: str
    attempt: int
    prompt: str
    system: str
    model_returned: str = ""
    response: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    stop_reason: str = ""
    problems: list[str] = field(default_factory=list)
    rejected: dict[str, list[str]] = field(default_factory=dict)
    accepted_keys: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self, timestamp: datetime) -> dict[str, Any]:
        return {"timestamp": timestamp.isoformat(timespec="seconds"), **self.__dict__}


def write_log(
    paths: ProjectPaths,
    record: RequestLog,
    now: Callable[[], datetime] = datetime.now,
) -> Path:
    paths.logs.mkdir(parents=True, exist_ok=True)
    stamp = now()
    base = f"{record.part_id}_{record.column}_{record.attempt}_{stamp:%Y%m%d_%H%M%S}"
    path = paths.logs / f"{base}.json"
    n = 1
    while path.exists():
        path = paths.logs / f"{base}_{n}.json"
        n += 1
    path.write_text(
        json.dumps(record.to_dict(stamp), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def list_logs(paths: ProjectPaths, part_id: str | None = None) -> Sequence[Path]:
    if not paths.logs.exists():
        return []
    pattern = f"{part_id}_*.json" if part_id else "*.json"
    return sorted(paths.logs.glob(pattern))
