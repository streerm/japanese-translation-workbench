You are translating a Japanese literary work into English: **{work_title}**.

## What you are being given

{part_header}

The segments below are a continuous passage, given in reading order. Each one is usually a
single sentence or a single line of dialogue. Read the whole passage before you start so you
can hold one voice across it, but translate every segment separately.

## Translation instructions

- Translate faithfully and idiomatically into natural, publishable English prose.
- Keep the meaning, tone and register of each segment. Do not summarise, censor or add.
- Keep each segment's boundaries. A sentence fragment stays a fragment; a line of dialogue
  stays a line of dialogue. Never move text from one segment into another.
- Keep names, terms and forms of address consistent across the passage.

### Style notes for this work

{style_notes}

### Glossary

Use these renderings wherever the source term appears:

{glossary}

## Output format: strict, and checked by a program

- Return exactly one translated block per input segment, in the same order as the input.
- Begin each block with its segment key reproduced character for character, alone on its own
  line, for example `[S012]`: no bold, no colon, no numbering, no other text on that line.
- Return all {segment_count} keys. Do not merge two segments under one key, split one segment
  across two keys, skip a key or invent a key.
- Output nothing else: no preamble, no commentary, no notes about your choices, no markdown
  code fences, no closing summary.
- Output English only. Do not echo the Japanese.

Example of the expected shape:

[S007]
He was tired, and had earned the right to be.

[S008]
"What do you want?"

## The segments to translate

{segments}
