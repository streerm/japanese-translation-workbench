# Prompt templates

Every prompt the workbench sends is rendered from a template file. The defaults are in the
repository's [`prompts/`](../prompts/) directory. They are deliberately generic: they carry
the *protocol* (segment keys, output format, no merging or splitting) and leave everything
about a particular work to slots filled from `project.toml`.

| Template | Used by | Purpose |
|---|---|---|
| `translate.md` | `jtw translate` | One part, sent to each MT column. |
| `repair.md` | `jtw translate` | Only the rejected segments, with what went wrong. |
| `draft.md` | 🧠 in the grid | Combine the MT columns into a first draft. |
| `deep_dive.md` | ✨ Deep Dive | First revision against the translator's notes. |
| `clipboard.txt` | 📋 Copy segments | Layout of copied segment text. |

## Slots

Placeholders are `{name}`. Only the names below are substituted; any other braces in a
template are left as they are.

| Slot | Filled with | Templates |
|---|---|---|
| `{work_title}` | `[work] title` | all prompts |
| `{style_notes}` | `[prompts] style_notes`, or `(none)` | all prompts |
| `{glossary}` | `[glossary]` as `- 原語 → rendering` lines, or `(none)` | all prompts |
| `{part_header}` | e.g. `**Part 2 of 7** (Chapter 1 · Part 2): 45 segment(s), 2,480 characters, S001–S045` | translate, repair |
| `{segments}` | The segments under their `[S001]` keys (with MT references and the current draft for draft/Deep Dive) | translate, repair, draft, deep_dive |
| `{segment_count}` | How many segments are in this request | translate, repair, draft, deep_dive |
| `{problem}` | The parser's description of what was rejected | repair |
| `{notes}` | The translator's notes | deep_dive |

`clipboard.txt` has its own slots: `{source}`, `{references}` (one `Label: text` line per MT
column), `{current_draft}` and `{comment}`. A line whose slots are all empty is left out.

Deep Dive follow-up turns (after the first revision) continue the same conversation with a
short built-in message containing the new notes.

## Overriding a template for one project

Copy the default into the project and point `project.toml` at it:

```bash
mkdir -p projects/my-work/prompts
cp prompts/translate.md projects/my-work/prompts/
```

```toml
[prompts]
translate = "prompts/translate.md"      # relative to projects/my-work/
style_notes = """
Narrator: first person, past tense. American English. Imperial units.
Western name order for Japanese names.
"""
```

Keep the output-format section intact: the parser enforces it whatever the prompt says, and
a prompt that asks for something else only produces more repair passes.

## Where work-specific context goes

| Kind of guidance | Put it in |
|---|---|
| Voice, tense, spelling variety, units, name order, punctuation policy | `[prompts] style_notes` |
| Fixed renderings of names and terms | `[glossary]` |
| Genre or background a model should know | `style_notes`, or an overridden template |

Projects are untracked by git, so none of this leaves your machine unless you choose to
commit it.
