from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jtw.mt.protocol import Problem, marker, parse_response, render_segments

KEYS = ["S001", "S002", "S003"]
EN = {"S001": "I woke at seven.", "S002": "Rain was falling.", "S003": '"Morning," she said.'}


def test_render_segments() -> None:
    assert marker("S007") == "[S007]"
    assert render_segments({"S001": "一。", "S002": "二。"}) == "[S001]\n一。\n\n[S002]\n二。"


def _bare() -> str:
    return "\n\n".join(f"[{k}]\n{v}" for k, v in EN.items())


LENIENT = {
    "bare": _bare(),
    "bold": "\n\n".join(f"**[{k}]**\n{v}" for k, v in EN.items()),
    "bold colon same line": "\n".join(f"**[{k}]:** {v}" for k, v in EN.items()),
    "colon": "\n".join(f"[{k}]: {v}" for k, v in EN.items()),
    "same line": "\n".join(f"[{k}] {v}" for k, v in EN.items()),
    "spaced and lowercase": "\n".join(f"[ s{k[1:]} ]\n{v}" for k, v in EN.items()),
    "heading": "\n".join(f"### [{k}]\n{v}" for k, v in EN.items()),
    "fenced": f"```text\n{_bare()}\n```",
    "preamble": f"Here is the translation you asked for:\n\n{_bare()}",
    "epilogue": f"{_bare()}\n\nLet me know if you would like any changes.",
    "epilogue after rule": f"{_bare()}\n---\nNotes: I kept the tone neutral.",
    "crlf": _bare().replace("\n", "\r\n"),
    "everything": (
        "Sure!\r\n```\r\n"
        + "\r\n".join(f"**[{k}]**: {v}" for k, v in EN.items())
        + "\r\n```\r\nHope this helps."
    ),
}


@pytest.mark.parametrize("name", list(LENIENT))
def test_lenient_presentation_is_accepted(name: str) -> None:
    result = parse_response(LENIENT[name], KEYS)
    assert result.ok, result.problems.describe()
    assert result.translations == EN


def test_multiline_interior_block_keeps_lines() -> None:
    result = parse_response("[S001]\nLine one.\nLine two.\n\n[S002]\nB.\n[S003]\nC.", KEYS)
    assert result.translations["S001"] == "Line one.\nLine two."


def _one(text: str, keys: list[str] = KEYS) -> dict[str, list[str]]:
    result = parse_response(text, keys)
    assert not result.ok
    return result.problems.as_dict()


@pytest.mark.parametrize(
    ("text", "expected", "accepted"),
    [
        ("[S001]\nA.\n[S002]\nB.", {"missing": ["S003"]}, ["S001", "S002"]),
        ("[S001]\nA.\n[S003]\nC.", {"merged": ["S002"]}, ["S001", "S003"]),
        ("[S002]\nB.\n[S003]\nC.", {"missing": ["S001"]}, ["S002", "S003"]),
        ("[S001]\nA.\n[S002]\n\n[S003]\nC.", {"empty": ["S002"]}, ["S001", "S003"]),
        (
            "[S001]\nA.\n[S002]\nB.\n[S002]\nB again.\n[S003]\nC.",
            {"duplicate": ["S002"]},
            ["S001", "S003"],
        ),
        ("[S001]\nA.\n[S002]\nB.\n[S003]\nC.\n[S004]\nD.", {"invented": ["S004"]}, KEYS),
        ("[S000]\nZ.\n[S001]\nA.\n[S002]\nB.\n[S003]\nC.", {"invented": ["S000"]}, KEYS),
        (
            "[S001]\nA.\n[S002]\n窓の外では雨が降っていた。\n[S003]\nC.",
            {"untranslated": ["S002"]},
            ["S001", "S003"],
        ),
        (
            "[S001]\nA.\n[S002-S003]\nB and C together.",
            {"merged": ["S002", "S003"]},
            ["S001"],
        ),
        ("**[S001, S002]** A and B.\n[S003]\nC.", {"merged": ["S001", "S002"]}, ["S003"]),
        (
            "[S001]\nA.\n[S003–S004]\nC.",
            {"merged": ["S002", "S003"], "invented": ["S004"]},
            ["S001"],
        ),
    ],
)
def test_strict_rejections(text: str, expected: dict[str, list[str]], accepted: list[str]) -> None:
    result = parse_response(text, KEYS)
    assert result.problems.as_dict() == expected
    assert sorted(result.translations) == accepted


def test_no_markers() -> None:
    result = parse_response("I'm sorry, I can't help with that.", KEYS)
    assert result.problems.no_markers
    assert result.problems.keys(Problem.MISSING) == KEYS
    assert "no [Snnn] segment keys" in result.problems.describe()
    assert parse_response("", KEYS).translations == {}


def test_describe_lists_every_category() -> None:
    text = "[S001]\n\n[S002]\n雨が降っていた。\n[S002]\nx\n[S009]\nx"
    problems = parse_response(text, ["S001", "S002", "S003"]).problems
    assert problems.describe().splitlines() == [
        "keys returned more than once: S002",
        "keys not requested: S009",
        "keys returned with no translation: S001",
        "keys not returned at all: S003",
    ]


def test_subset_of_keys_for_repair_pass() -> None:
    result = parse_response("[S002]\nB.", ["S002"])
    assert result.ok and result.translations == {"S002": "B."}


_word = st.text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJ", min_size=1, max_size=10)
_sentence = st.lists(_word, min_size=1, max_size=8).map(lambda ws: " ".join(ws) + ".")
_decor = st.sampled_from(["[{k}]\n", "**[{k}]**\n", "[{k}]: ", "**[{k}]:** ", "[{k}] "])


@given(
    st.lists(_sentence, min_size=1, max_size=30),
    st.lists(_decor, min_size=30, max_size=30),
    st.sampled_from(["", "Here you go:\n\n", "```\n"]),
    st.sampled_from(["\n", "\n\n", "\r\n"]),
)
def test_property_round_trip(
    sentences: list[str], decor: list[str], preamble: str, sep: str
) -> None:
    keys = [f"S{i:03d}" for i in range(1, len(sentences) + 1)]
    body = sep.join(
        decor[i].format(k=k) + s for i, (k, s) in enumerate(zip(keys, sentences, strict=True))
    )
    result = parse_response(preamble + body, keys)
    assert result.ok, result.problems.describe()
    assert result.translations == dict(zip(keys, sentences, strict=True))
