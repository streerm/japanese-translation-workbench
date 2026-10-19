"""Every Japanese-specific regex and heuristic in the package lives in this module.

Keeping them together makes the language assumptions easy to audit, and easy to replace if
another source language is ever supported.
"""

from __future__ import annotations

import re

#: Hiragana, katakana (incl. the prolonged-sound mark), CJK unified ideographs and
#: extension A, the iteration mark 々, and half-width katakana.
CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿々ｦ-ﾟ]")

#: A block whose share of Japanese characters reaches this ratio is treated as untranslated.
UNTRANSLATED_RATIO = 0.25

#: Sentence-final punctuation for segmentation.
SENTENCE_END = "。！？!?"
#: Closing brackets that stay attached to the sentence they close.
CLOSING_BRACKETS = "」』）)】〉》"
#: Opening/closing pairs that mark a line of dialogue.
DIALOGUE_OPEN = "「『"
DIALOGUE_CLOSE = "」』"

#: Brackets that suspend sentence splitting until they close.
OPENING_BRACKETS = "「『（(【〈《"
BRACKET_PAIRS = dict(zip(OPENING_BRACKETS, CLOSING_BRACKETS, strict=True))

#: A line that is a chapter heading: 第一章, 第3話 タイトル, 序章, プロローグ, a bare numeral...
HEADING_RE = re.compile(
    r"^(?:第[0-9０-９一二三四五六七八九十百千]+[章話部節幕]|序章|終章|序|"
    r"プロローグ|エピローグ|あとがき|[0-9０-９]+|[一二三四五六七八九十]+)"
    r"(?:[ 　・:：．.、]+.*)?$"
)
HEADING_MAX_CHARS = 40

_SPACE_RE = re.compile(r"\s+")


def cjk_ratio(text: str) -> float:
    """Share of non-whitespace characters that are Japanese script."""
    compact = _SPACE_RE.sub("", text)
    if not compact:
        return 0.0
    return len(CJK_RE.findall(compact)) / len(compact)


def looks_untranslated(text: str, ratio: float = UNTRANSLATED_RATIO) -> bool:
    """True if ``text`` is substantially Japanese, i.e. the model echoed the source.

    A few Japanese characters in an English sentence (a name in kanji, a sound effect) stay
    well under the threshold.
    """
    return cjk_ratio(text) >= ratio


def char_count(text: str) -> int:
    """Manuscript length of Japanese text: every character except whitespace.

    Japanese is measured in characters rather than words; punctuation and brackets count,
    line breaks and spaces do not.
    """
    return len(_SPACE_RE.sub("", text))


def is_heading(line: str) -> bool:
    """True for a short line that looks like a chapter heading and is not a sentence."""
    stripped = line.strip()
    if not stripped or len(stripped) > HEADING_MAX_CHARS:
        return False
    if stripped[-1] in SENTENCE_END + "」』":
        return False
    return HEADING_RE.match(stripped) is not None


def join_lines(lines: list[str]) -> str:
    """Join the lines of one Japanese paragraph: no spaces between them."""
    return "".join(line.strip() for line in lines)
