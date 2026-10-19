# Data model

Everything a project holds is plain JSON or TOML under `projects/<slug>/`, readable and
diffable without the workbench. This page documents each file. Code:
[`src/jtw/model/`](../src/jtw/model/), [`src/jtw/config.py`](../src/jtw/config.py).

```
projects/<slug>/
├── project.toml                      # configuration (see docs/prompts.md for [prompts])
├── source.json                       # read-only source, written once by `jtw ingest`
├── saves/<part>.latest.json          # the working state of one part
├── saves/<part>.<YYYYMMDD_HHMMSS>.json   # rotating backups (newest `keep_saves` kept)
├── logs/<part>_<column>_<attempt>_<ts>.json  # one per MT request
├── tmp/deep_dive_<part>_<first>-<last>.json  # Deep Dive sessions
└── exports/*.docx
```

## Terms

| Term | Meaning |
|---|---|
| **Segment** | The unit of translation: usually one sentence or one line of dialogue. Keyed `S001`, `S002`, ... within its part. |
| **Part** | A continuous passage of a few thousand characters: the unit of one MT request and one save file. Ids are filename-safe, e.g. `C01P02`. |
| **Chapter** | An optional grouping of consecutive parts, for navigation. |
| **MT column** | One machine-translation model's output, named by a column id from `project.toml` (`[mt] columns`). |
| **Reference** | `C01P02/S014`: a part id and segment key. Used in search results and logs. |

## `project.toml`

```toml
[work]
slug = "demo"                  # must equal the directory name
title = "Demo Story"           # English working title
title_source = "デモ物語"       # title in the original script
author = "Author Name"
translator = "Your Name"
source_lang = "ja"             # only ja → en is supported
target_lang = "en"

[mt]
columns = ["gpt", "opus"]      # run order and grid order

[mt.column.gpt]
label = "GPT-6 Astra"
provider = "openai"            # "anthropic" or "openai"
model = "gpt-6-astra"

[mt.column.opus]
label = "Opus 5"
provider = "anthropic"
model = "claude-opus-5"

[synthesis]
draft     = { provider = "anthropic", model = "claude-opus-5" }
deep_dive = { provider = "anthropic", model = "claude-opus-5" }

[prompts]
style_notes = "First person, past tense. American English."
# translate = "prompts/translate.md"   # optional per-project template overrides

[glossary]
"固有名詞" = "Proper Noun"

[limits]
max_tokens_part = 32000        # output ceiling for an MT request (thinking included)
max_tokens_default = 16000     # output ceiling for draft and Deep Dive
request_timeout_s = 1800
repair_passes = 2
keep_saves = 10
```

Validation rejects unknown keys, a column listed without a `[mt.column.<id>]` table (or the
reverse), column ids that are not `[a-z][a-z0-9_]*` or that collide with segment field names,
unknown providers and empty model strings. Every error names its TOML path, e.g.
`mt.column.gpt.provider: Input should be 'anthropic' or 'openai'`. API keys never go in this
file: they come from `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` in the environment or `.env`.

## `source.json`

The source text, read-only. The workbench never writes it; corrections to the source text
are stored in the part's save (see the merge rule below).

```jsonc
{
  "schema": 1,
  "parts": [
    {
      "id": "C01P01",                  // stable, filename-safe
      "label": "Chapter 1 · Part 1",   // shown in the sidebar
      "chapter": "1",                  // optional grouping key
      "chapter_title": "第一章　朝",     // optional
      "segments": [
        { "key": "S001", "source": "朝の七時に目が覚めた。" },
        { "key": "S002", "source": "窓の外では雨が静かに降っていた。" }
      ]
    }
  ]
}
```

Keys restart at `S001` in every part and must be unique and in order.

### How `jtw ingest` builds it

`jtw ingest <slug> <file.txt> [--part-chars 2500] [--split-on-headings] [--encoding utf-8]`
applies these rules (all Japanese-specific heuristics live in
[`src/jtw/text/ja.py`](../src/jtw/text/ja.py)):

1. **Paragraphs.** A blank line separates paragraphs; the lines of one paragraph are joined
   without spaces. A file with no blank lines at all is read as one paragraph per line.
2. **Sentences.** A paragraph is split after `。！？` (and `!?`), keeping closing brackets
   `」』）` attached to the sentence they close. Nothing inside brackets is split.
3. **Dialogue.** A line of dialogue `「…」` is its own segment when nothing follows the closing
   bracket except another line of dialogue or the end of the paragraph. `「…」と言った。`
   stays a single segment.
4. **Parts.** Paragraphs are grouped into parts, cutting at the paragraph boundary nearest
   `--part-chars` Japanese characters. Without headings, parts are `P01`, `P02`, ...
5. **Chapters.** With `--split-on-headings`, a short line such as `第一章`, `第3話 出発`,
   `序章` or `プロローグ` starts a new chapter and becomes its title (not a segment). Parts are
   then `C01P01`, `C01P02`, `C02P01`, ...; any text before the first heading is chapter 0.

Character counts (`jtw stats`, the part budget) count every character except whitespace,
the usual way Japanese manuscripts are measured.

## Save files

`saves/<part_id>.latest.json` holds the working state of one part:

```jsonc
{
  "schema": 1,
  "metadata": {
    "part_id": "C01P01",
    "saved_at": "2026-10-19T15:04:05",
    "note": "translate gpt",
    "total_segments": 45,
    "finalized_segments": 12
  },
  "segments": {
    "S001": {
      "source": "…",                       // may hold a corrected source
      "mt": { "gpt": "…", "opus": "…" },   // one entry per configured column
      "final": "…",                        // the translator's text
      "notes": "…",
      "is_finalized": false,
      "merge_with_next": false             // join with the next segment in exports
    }
  }
}
```

Every save writes a timestamped copy and the `latest` file, each atomically (temporary file
and rename), then deletes all but the newest `keep_saves` timestamped copies.

**Merge rule on load.** The save wins. For a segment in both, every field comes from the
save; the source only supplies the `source` text when the save has none. Source segments not
yet in the save are added blank. Saved segments the source no longer has are kept, after the
others, and reported as *orphans* by `jtw stats`: nothing is silently dropped. MT text for a
column the project no longer has is dropped with a warning.

**Merge chains.** A run of segments where each but the last has `merge_with_next` is a
chain. Word export prints a chain as one paragraph, the clipboard copy as one block, and the
grid shades it.

## MT request logs

`logs/<part>_<column>_<attempt>_<YYYYMMDD_HHMMSS>.json`, one per request:

```jsonc
{
  "timestamp": "2026-10-19T15:04:05",
  "part_id": "C01P01", "column": "gpt", "provider": "openai",
  "model_requested": "gpt-6-astra", "model_returned": "gpt-6-astra-2026-09-01",
  "attempt": 1,                     // 2+ are repair passes
  "system": "…", "prompt": "…", "response": "…",
  "usage": { "input_tokens": 0, "output_tokens": 0 },
  "stop_reason": "completed",
  "problems": ["keys not returned at all: S044, S045"],
  "rejected": { "missing": ["S044", "S045"] },
  "accepted_keys": ["S001", "…"],
  "error": null                     // e.g. a model mismatch
}
```

## Deep Dive sessions

`tmp/deep_dive_<part>_<first>-<last>.json`, saved after every iteration:

```jsonc
{
  "schema": 1,
  "part_id": "C01P01",
  "keys": ["S002", "S003"],
  "iterations": [
    { "notes": "…", "response": "…", "revisions": { "S002": "…" },
      "commentary": "…", "problems": "" }
  ],
  "messages": [ { "role": "user", "content": "…" }, { "role": "assistant", "content": "…" } ]
}
```
