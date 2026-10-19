# The MT protocol and its failsafe

Bulk machine translation is only useful if every source segment comes back as exactly one
translated segment. A model that quietly merges two sentences, skips a line of dialogue or
echoes the Japanese breaks the one-to-one mapping the editing grid depends on. This
document describes the contract `jtw translate` holds every model to, and what happens when
a model breaks it.

Code: [`src/jtw/mt/protocol.py`](../src/jtw/mt/protocol.py) (parser),
[`src/jtw/text/ja.py`](../src/jtw/text/ja.py) (the untranslated check).

## Request unit: one part per model

A request carries one whole *part*: a continuous passage of up to a few thousand Japanese
characters. Sending a part rather than single sentences lets the model hold one voice, keep
pronouns and tense consistent, and read a line of dialogue in context. Each MT column (one
model) translates the part independently.

## The contract

Every segment is sent under its key on a line of its own:

```text
[S001]
朝の七時に目が覚めた。

[S002]
窓の外では雨が静かに降っていた。
```

The prompt requires the reply to reproduce every key character for character, one block per
key, in the same order: no merging, splitting or omitting; fragments stay fragments; no
preamble, commentary or code fences.

## Lenient about presentation

Models embellish. Failing a whole part over punctuation wastes money, so the parser accepts:

| Variation | Example |
|---|---|
| Bold or italic key | `**[S001]**` |
| Trailing colon | `[S001]:` / `**[S001]:**` |
| Text on the key line | `[S001] I woke at seven.` |
| Heading or list mark | `### [S001]` / `- [S001]` |
| Lower case and spaces | `[ s001 ]` |
| Code fences | ```` ```text … ``` ```` around the whole reply |
| Preamble | `Here is the translation:` before the first key |
| Sign-off | `Let me know if…` after the last block (cut at the first blank line or `---`) |
| Line endings | CRLF or CR |

## Strict about substance

A key is **accepted** only if it was requested, appears exactly once, is not fused with a
neighbour, and holds non-empty text that is not substantially Japanese. Every other key is
rejected under one of six categories:

| Category | Meaning | Example reply fragment |
|---|---|---|
| `missing` | Never returned, before the first or after the last returned key (a skipped opening, or truncation). | reply stops after `[S002]` |
| `merged` | Fused into a neighbour: a combined marker, or a gap between returned keys. | `[S002-S003]` or `[S001]` … `[S003]` |
| `empty` | Key present, no text under it. | `[S002]` followed directly by `[S003]` |
| `duplicate` | Key returned more than once (neither copy is trusted). | `[S002]` twice |
| `invented` | Key that was not requested. | `[S004]` in a three-segment request |
| `untranslated` | At least 25 % of the non-space characters are Japanese script. | `[S002]` `窓の外では雨が…` |

The 25 % threshold lets an English sentence keep a name in kanji or a quoted sound effect
while catching a model that echoed the source.

### Worked example: accepted

```text
Sure! Here's the passage:

**[S001]:** I woke at seven in the morning.
**[S002]:** Outside the window, rain was falling softly.

Let me know if you'd like a more formal register.
```

Both keys accepted; the preamble and sign-off are discarded.

### Worked example: rejected

Request: `S001`–`S004`.

```text
[S001]
I woke at seven in the morning.

[S002-S003]
Outside the window, rain was falling softly, and my sister said, "Morning."
```

Result: `S001` accepted; `S002`, `S003` rejected as `merged`; `S004` rejected as `missing`.
The problem description sent back to the model reads:

```text
keys merged with a neighbouring segment: S002, S003
keys not returned at all: S004
```

## Repair and resume

1. Whatever was accepted is saved to the part's save file **immediately**.
2. The rejected keys alone are sent again in a *repair* request (default two passes), with
   the problem description, so the model knows exactly what went wrong.
3. Keys still rejected after the last pass stay blank. `jtw translate` exits non-zero and
   prints a summary.
4. Re-running the same command skips every cell that already has text, so it resumes rather
   than re-translating (and re-paying for) the whole part.

## Provenance: the model-mismatch guard

Every response reports the model that served it. If that is not the requested model, or a
dated snapshot of it (`claude-opus-5-20260101` for `claude-opus-5`, `gpt-6-astra-2026-01-01`
for `gpt-6-astra`), the response is discarded and logged. A column labelled with one model
never silently holds another model's output.

## No accidental spend

`jtw translate` requires `--parts` or `--all`; there is no default that calls an API.
`--dry-run` prints the rendered prompt and calls nothing.
