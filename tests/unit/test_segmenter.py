import pytest

from jtw.text.ja import is_heading
from jtw.text.segmenter import build_structure, paragraphs, sentences


@pytest.mark.parametrize(
    ("paragraph", "expected"),
    [
        ("朝だ。雨だ。", ["朝だ。", "雨だ。"]),
        ("本当に？　嘘だろう！？", ["本当に？", "嘘だろう！？"]),
        ("「おはよう」と姉が言った。", ["「おはよう」と姉が言った。"]),
        ("「おはよう」「はい」", ["「おはよう」", "「はい」"]),
        ("「一つ。二つ。」", ["「一つ。二つ。」"]),
        ("彼は言った。「待って！」そして走った。", ["彼は言った。", "「待って！」そして走った。"]),
        ("『本の名前』を読んだ。", ["『本の名前』を読んだ。"]),
        ("終わりのない文", ["終わりのない文"]),
        ("閉じない「括弧。の文", ["閉じない「括弧。の文"]),
        ("Wow!? Yes.", ["Wow!?", "Yes."]),
    ],
)
def test_sentences(paragraph: str, expected: list[str]) -> None:
    assert sentences(paragraph) == expected


def test_paragraphs_blank_lines_and_line_joining() -> None:
    text = "﻿朝の\n七時だ。\r\n\r\n「おはよう」\n\n\n雨。"
    assert [p.text for p in paragraphs(text)] == ["朝の七時だ。", "「おはよう」", "雨。"]


def test_paragraphs_one_per_line_without_blank_lines() -> None:
    assert [p.text for p in paragraphs("一行目。\n二行目。\n")] == ["一行目。", "二行目。"]


@pytest.mark.parametrize(
    ("line", "heading"),
    [
        ("第一章", True),
        ("第3話　出発", True),
        ("序章", True),
        ("プロローグ", True),
        ("１", True),
        ("二", True),
        ("第一章で彼は言った。", False),
        ("一番目の話をしよう", False),
        ("x" * 50, False),
        ("", False),
    ],
)
def test_is_heading(line: str, heading: bool) -> None:
    assert is_heading(line) is heading


def test_parts_cut_at_nearest_paragraph_boundary() -> None:
    para = "あ" * 9 + "。"  # 10 chars
    text = "\n\n".join([para] * 7)
    structure = build_structure(text, part_chars=25)
    # 10+10=20; adding a third (30) overshoots by 5 vs undershoot 5 -> keep it: 30, then next.
    assert [len(p.segments) for p in structure.parts] == [3, 3, 1]
    assert structure.ids == ["P01", "P02", "P03"]
    assert structure.parts[0].label == "Part 1"
    assert structure.parts[0].keys == ["S001", "S002", "S003"]
    assert structure.parts[0].chapter is None


def test_parts_cut_before_when_closer() -> None:
    short, long = "あ。", "い" * 29 + "。"
    structure = build_structure(f"{short}\n\n{long}\n\n{short}", part_chars=10)
    assert [len(p.segments) for p in structure.parts] == [1, 1, 1]


def test_split_on_headings() -> None:
    text = "前書き。\n\n第一章　朝\n\n朝だ。\n\n「おはよう」\n\n第二章\n\n駅に行った。"
    structure = build_structure(text, part_chars=1000, split_on_headings=True)
    assert structure.ids == ["C00P01", "C01P01", "C02P01"]
    first = structure.parts[1]
    assert first.chapter == "1" and first.chapter_title == "第一章　朝"
    assert [s.source for s in first.segments] == ["朝だ。", "「おはよう」"]
    assert structure.parts[0].chapter_title is None
    assert [c.id for c in structure.chapters()] == ["0", "1", "2"]


def test_headings_ignored_without_flag_and_errors() -> None:
    assert build_structure("第一章\n\n朝だ。").parts[0].segments[0].source == "第一章"
    with pytest.raises(ValueError):
        build_structure("第一章", split_on_headings=True)
    with pytest.raises(ValueError):
        build_structure("x", part_chars=0)
