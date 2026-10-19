import pytest

from jtw.text.ja import char_count, cjk_ratio, looks_untranslated


@pytest.mark.parametrize(
    ("text", "untranslated"),
    [
        ("朝の七時に目が覚めた。", True),
        ("I woke at seven.", False),
        ("She said 「はい」 and left the room quietly.", False),
        ("Hello. 窓の外では雨が降っていた。", True),
        ("ｶﾀｶﾅ", True),
        ("", False),
        ("   ", False),
    ],
)
def test_looks_untranslated(text: str, untranslated: bool) -> None:
    assert looks_untranslated(text) is untranslated


def test_ratio_threshold_is_inclusive() -> None:
    assert cjk_ratio("あbcd") == 0.25
    assert looks_untranslated("あbcd")
    assert not looks_untranslated("あbcde")


def test_char_count_ignores_whitespace() -> None:
    assert char_count("「おはよう」\n と言った。") == 11
    assert char_count("") == 0
