import logging

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jtw.model.segment import (
    Segment,
    is_segment_key,
    key_index,
    normalize,
    ordered_keys,
    segment_key,
)

COLUMNS = ("alpha", "beta")


def test_segment_key_round_trip() -> None:
    assert segment_key(1) == "S001"
    assert segment_key(1234) == "S1234"
    assert key_index("S012") == 12
    with pytest.raises(ValueError):
        segment_key(0)
    with pytest.raises(ValueError):
        key_index("segment_001")


def test_ordered_keys_sorts_numerically_and_drops_others() -> None:
    assert ordered_keys(["S010", "S002", "meta", "S1000", "S001"]) == [
        "S001",
        "S002",
        "S010",
        "S1000",
    ]
    assert not is_segment_key("S01")


def test_normalize_fills_and_coerces() -> None:
    out = normalize({"final": None, "is_finalized": "true", "mt": {"alpha": 3}}, COLUMNS)
    assert out == {
        "source": "",
        "final": "",
        "notes": "",
        "mt": {"alpha": "3", "beta": ""},
        "is_finalized": True,
        "merge_with_next": False,
    }


def test_normalize_non_mapping() -> None:
    assert normalize("junk", COLUMNS)["mt"] == {"alpha": "", "beta": ""}


def test_normalize_drops_unknown_columns_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        out = normalize({"mt": {"alpha": "a", "gone": "g"}}, COLUMNS)
    assert out["mt"] == {"alpha": "a", "beta": ""}
    assert "gone" in caplog.text


def test_segment_round_trip() -> None:
    seg = Segment(key="S003", source="源", mt={"alpha": "a", "beta": "b"}, final="f")
    again = Segment.from_raw("S003", seg.to_dict(), COLUMNS)
    assert again == seg
    assert again.ref_index == 3


_values = st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=8))
_raw = st.one_of(
    _values,
    st.dictionaries(
        st.sampled_from(["source", "final", "notes", "is_finalized", "merge_with_next", "x"]),
        _values,
    ),
    st.fixed_dictionaries(
        {"mt": st.dictionaries(st.sampled_from(["alpha", "beta", "gamma"]), _values)}
    ),
)


@given(_raw)
def test_normalize_is_idempotent(raw: object) -> None:
    once = normalize(raw, COLUMNS)
    assert normalize(once, COLUMNS) == once
