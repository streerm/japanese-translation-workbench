"""Reading the read-only source and reading/writing per-part saves.

``source.json`` is never written by the workbench. Each part has its own save,
``saves/<part_id>.latest.json``, plus timestamped copies of which the newest ``keep`` are kept.

Merge rule on load: the save wins. For a segment present in both, every field comes from the
save; the source only supplies ``source`` text when the save has none recorded. Source segments
missing from the save are added blank. Saved segments the source no longer has are kept (after
the source segments) and reported as orphans, never dropped silently.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from jtw.model.part import PART_ID_RE, Part, SourceSegment, Structure
from jtw.model.segment import Segment, is_segment_key, ordered_keys
from jtw.paths import ProjectPaths

SCHEMA_VERSION = 1
DEFAULT_KEEP_SAVES = 10
_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"


class StoreError(ValueError):
    """A source or save file is malformed."""


@dataclass
class LoadedPart:
    """The working set for one part: source with its latest save layered on top."""

    part: Part
    segments: dict[str, Segment]
    orphans: list[str] = field(default_factory=list)

    @property
    def keys(self) -> list[str]:
        return list(self.segments)

    @property
    def finalized_count(self) -> int:
        return sum(1 for s in self.segments.values() if s.is_finalized)


# --- source -----------------------------------------------------------------


def load_source(paths: ProjectPaths) -> Structure:
    """Parse and validate ``source.json``."""
    try:
        data = json.loads(paths.source_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise StoreError(f"{paths.source_file} not found; run `jtw ingest` first") from None
    except json.JSONDecodeError as exc:
        raise StoreError(f"{paths.source_file}: invalid JSON ({exc})") from exc
    return parse_source(data, origin=str(paths.source_file))


def parse_source(data: object, origin: str = "source") -> Structure:
    if not isinstance(data, Mapping):
        raise StoreError(f"{origin}: top level must be an object")
    if data.get("schema") != SCHEMA_VERSION:
        raise StoreError(f"{origin}: unsupported schema {data.get('schema')!r}")
    raw_parts = data.get("parts")
    if not isinstance(raw_parts, list):
        raise StoreError(f"{origin}: 'parts' must be a list")
    parts = [_parse_part(raw, f"{origin}: parts[{i}]") for i, raw in enumerate(raw_parts)]
    try:
        return Structure(tuple(parts))
    except ValueError as exc:
        raise StoreError(f"{origin}: {exc}") from exc


def _parse_part(raw: object, where: str) -> Part:
    if not isinstance(raw, Mapping):
        raise StoreError(f"{where} must be an object")
    part_id = raw.get("id")
    if not isinstance(part_id, str) or not PART_ID_RE.match(part_id):
        raise StoreError(f"{where}.id must be a filename-safe string, got {part_id!r}")
    raw_segments = raw.get("segments")
    if not isinstance(raw_segments, list):
        raise StoreError(f"{where}.segments must be a list")
    segments: list[SourceSegment] = []
    for j, seg in enumerate(raw_segments):
        if not isinstance(seg, Mapping):
            raise StoreError(f"{where}.segments[{j}] must be an object")
        key, source = seg.get("key"), seg.get("source")
        if not isinstance(key, str) or not is_segment_key(key):
            raise StoreError(f"{where}.segments[{j}].key must look like 'S001', got {key!r}")
        if not isinstance(source, str):
            raise StoreError(f"{where}.segments[{j}].source must be a string")
        segments.append(SourceSegment(key, source))
    keys = [s.key for s in segments]
    if len(set(keys)) != len(keys):
        raise StoreError(f"{where}: duplicate segment keys")
    if keys != ordered_keys(keys):
        raise StoreError(f"{where}: segment keys are not in order")

    def optional(name: str) -> str | None:
        value = raw.get(name)
        return None if value is None else str(value)

    return Part(
        id=part_id,
        label=str(raw.get("label") or part_id),
        segments=tuple(segments),
        chapter=optional("chapter"),
        chapter_title=optional("chapter_title"),
    )


def source_payload(structure: Structure) -> dict[str, Any]:
    """The JSON representation of a structure (used by ingestion)."""
    parts: list[dict[str, Any]] = []
    for part in structure.parts:
        entry: dict[str, Any] = {"id": part.id, "label": part.label}
        if part.chapter is not None:
            entry["chapter"] = part.chapter
        if part.chapter_title is not None:
            entry["chapter_title"] = part.chapter_title
        entry["segments"] = [{"key": s.key, "source": s.source} for s in part.segments]
        parts.append(entry)
    return {"schema": SCHEMA_VERSION, "parts": parts}


# --- saves ------------------------------------------------------------------


def read_save(paths: ProjectPaths, part_id: str) -> dict[str, Any] | None:
    """The raw latest save for a part, or ``None`` if it has never been saved."""
    path = paths.latest_save(part_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StoreError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(data, dict) or not isinstance(data.get("segments"), dict):
        raise StoreError(f"{path}: missing 'segments' object")
    return data


def merge_part(part: Part, save: Mapping[str, Any] | None, columns: Sequence[str]) -> LoadedPart:
    """Layer a save over a part's source according to the module's merge rule."""
    saved: Mapping[str, Any] = save["segments"] if save else {}
    segments: dict[str, Segment] = {}
    for src in part.segments:
        raw = saved.get(src.key)
        if raw is None:
            segments[src.key] = Segment(key=src.key, source=src.source, mt=_blank_mt(columns))
            continue
        segment = Segment.from_raw(src.key, raw, columns)
        if not (isinstance(raw, Mapping) and "source" in raw):
            segment.source = src.source
        segments[src.key] = segment

    orphans = [k for k in ordered_keys(saved) if k not in segments]
    for key in orphans:
        segments[key] = Segment.from_raw(key, saved[key], columns)
    return LoadedPart(part=part, segments=segments, orphans=orphans)


def load_part(
    paths: ProjectPaths,
    part_id: str,
    columns: Sequence[str],
    structure: Structure | None = None,
) -> LoadedPart:
    structure = structure if structure is not None else load_source(paths)
    part = structure.part_by_id(part_id)
    return merge_part(part, read_save(paths, part_id), columns)


def save_part(
    paths: ProjectPaths,
    part_id: str,
    segments: Mapping[str, Segment],
    *,
    note: str = "",
    keep: int = DEFAULT_KEEP_SAVES,
    now: Callable[[], datetime] = datetime.now,
) -> Path:
    """Write a timestamped save and the ``latest`` copy, then rotate. Returns the timestamped path.

    Both files are written atomically (temporary file + rename), so a crash mid-write never
    leaves a truncated save behind.
    """
    paths.saves.mkdir(parents=True, exist_ok=True)
    stamp = now()
    keys = list(segments)
    payload = {
        "schema": SCHEMA_VERSION,
        "metadata": {
            "part_id": part_id,
            "saved_at": stamp.isoformat(timespec="seconds"),
            "note": note,
            "total_segments": len(keys),
            "finalized_segments": sum(1 for k in keys if segments[k].is_finalized),
        },
        "segments": {k: segments[k].to_dict() for k in keys},
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    timestamped = _free_name(paths.saves, part_id, stamp.strftime(_TIMESTAMP_FORMAT))
    _atomic_write(timestamped, text)
    _atomic_write(paths.latest_save(part_id), text)
    rotate_saves(paths, part_id, keep)
    return timestamped


def list_saves(paths: ProjectPaths, part_id: str) -> list[Path]:
    """Timestamped saves for a part, newest first."""
    if not paths.saves.exists():
        return []
    prefix = f"{part_id}."
    found = [
        p
        for p in paths.saves.glob(f"{part_id}.2*.json")
        if p.name.startswith(prefix) and p.name[len(prefix) : len(prefix) + 1].isdigit()
    ]
    return sorted(found, key=lambda p: p.name, reverse=True)


def rotate_saves(paths: ProjectPaths, part_id: str, keep: int) -> list[Path]:
    """Delete all but the newest ``keep`` timestamped saves. Returns what was removed."""
    removed = list_saves(paths, part_id)[max(keep, 0) :]
    for old in removed:
        old.unlink(missing_ok=True)
    return removed


def _blank_mt(columns: Sequence[str]) -> dict[str, str]:
    return {c: "" for c in columns}


def _free_name(directory: Path, part_id: str, stamp: str) -> Path:
    candidate = directory / f"{part_id}.{stamp}.json"
    n = 1
    while candidate.exists():
        candidate = directory / f"{part_id}.{stamp}_{n}.json"
        n += 1
    return candidate


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
