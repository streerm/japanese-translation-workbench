"""A segment is the smallest unit of translation: usually one sentence or one line of dialogue.

Each part numbers its segments ``S001``, ``S002``, ... in reading order. Every segment carries
its source text, one machine translation per configured MT column, the translator's final
text and notes, and two flags.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

KEY_RE = re.compile(r"^S(\d{3,})$")

#: Fields of a saved segment. MT column ids may never use these names.
RESERVED_FIELDS = frozenset(
    {"key", "source", "mt", "final", "notes", "is_finalized", "merge_with_next"}
)
_TEXT_FIELDS = ("source", "final", "notes")
_BOOL_FIELDS = ("is_finalized", "merge_with_next")


def segment_key(index: int) -> str:
    """1-based position -> ``"S001"``."""
    if index < 1:
        raise ValueError(f"segment index must be >= 1, got {index}")
    return f"S{index:03d}"


def key_index(key: str) -> int:
    """``"S012"`` -> ``12``. Raises ``ValueError`` for anything that is not a segment key."""
    match = KEY_RE.match(key)
    if not match:
        raise ValueError(f"not a segment key: {key!r}")
    return int(match.group(1))


def is_segment_key(key: str) -> bool:
    return KEY_RE.match(key) is not None


def ordered_keys(keys: Iterable[str]) -> list[str]:
    """Segment keys in reading order; anything that is not a segment key is dropped."""
    return sorted((k for k in keys if is_segment_key(k)), key=key_index)


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _as_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def normalize(raw: object, columns: Sequence[str]) -> dict[str, Any]:
    """Coerce a stored segment of any vintage into the canonical saved shape.

    Missing fields are filled with blanks, flags are coerced to ``bool``, ``mt`` gets exactly
    one entry per configured column (in column order), and MT entries for columns the project
    no longer has are dropped with a warning. The result is a fixed point:
    ``normalize(normalize(x, c), c) == normalize(x, c)``.
    """
    data: Mapping[str, object] = raw if isinstance(raw, Mapping) else {}
    out: dict[str, Any] = {name: _as_text(data.get(name)) for name in _TEXT_FIELDS}

    raw_mt = data.get("mt")
    mt_in: Mapping[str, object] = raw_mt if isinstance(raw_mt, Mapping) else {}
    unknown = sorted(str(k) for k in mt_in if k not in columns)
    if unknown:
        logger.warning("dropping MT text for unknown columns: %s", ", ".join(unknown))
    out["mt"] = {column: _as_text(mt_in.get(column)) for column in columns}

    for name in _BOOL_FIELDS:
        out[name] = _as_bool(data.get(name, False))
    return out


@dataclass
class Segment:
    """One segment of a part, as edited in the workbench."""

    key: str
    source: str = ""
    mt: dict[str, str] = field(default_factory=dict)
    final: str = ""
    notes: str = ""
    is_finalized: bool = False
    merge_with_next: bool = False

    @classmethod
    def from_raw(cls, key: str, raw: object, columns: Sequence[str]) -> Segment:
        data = normalize(raw, columns)
        return cls(key=key, **data)

    def to_dict(self) -> dict[str, Any]:
        """The saved representation (without the key, which is the dict key in a save)."""
        return {
            "source": self.source,
            "mt": dict(self.mt),
            "final": self.final,
            "notes": self.notes,
            "is_finalized": self.is_finalized,
            "merge_with_next": self.merge_with_next,
        }

    @property
    def ref_index(self) -> int:
        return key_index(self.key)
