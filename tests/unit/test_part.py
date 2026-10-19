import pytest

from jtw.model.part import Part, SourceSegment, Structure, qualified_ref


def _part(pid: str, chapter: str | None = None, title: str | None = None) -> Part:
    return Part(pid, f"label {pid}", (SourceSegment("S001", "一"),), chapter, title)


def _structure() -> Structure:
    return Structure(
        (_part("A", "1", "始"), _part("B", "1", "始"), _part("C", "2"), _part("D"), _part("E"))
    )


def test_lookup_and_labels() -> None:
    s = _structure()
    assert s.ids == ["A", "B", "C", "D", "E"]
    assert s.label("C") == "label C"
    assert s.part_by_id("A").keys == ["S001"]
    assert s.part_by_id("A").source_text("S001") == "一"
    with pytest.raises(KeyError):
        s.part_by_id("Z")
    with pytest.raises(KeyError):
        s.part_by_id("A").source_text("S009")
    assert qualified_ref("A", "S001") == "A/S001"


def test_duplicate_ids_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        Structure((_part("A"), _part("A")))


def test_chapters_group_consecutive_parts() -> None:
    chapters = _structure().chapters()
    assert [c.id for c in chapters] == ["1", "2", "D", "E"]
    assert [p.id for p in chapters[0].parts] == ["A", "B"]
    assert chapters[0].label == "Chapter 1 · 始"
    assert chapters[1].label == "Chapter 2"


def test_select_by_id_position_and_range() -> None:
    s = _structure()
    assert [p.id for p in s.select(["3", "A", "1"])] == ["A", "C"]
    assert [p.id for p in s.select(["2-4", " "])] == ["B", "C", "D"]
    for bad in (["9"], ["0"], ["4-2"], ["nope"]):
        with pytest.raises(ValueError):
            s.select(bad)
