You are preparing a first draft of a literary translation from Japanese into English:
**{work_title}**.

For each of the {segment_count} segment(s) below you are given the Japanese source and one or
more independent machine translations ("references"). Write the best English rendering of
each segment: faithful to the Japanese, natural and publishable in English. Use the
references as evidence, not as candidates to pick from; where they disagree, the Japanese
decides. Keep `**bold**` and `*italic*` markup where the source calls for emphasis.

The segments are consecutive and belong to one passage, so keep voice and terminology
consistent across them, but return each segment separately.

### Style notes for this work

{style_notes}

### Glossary

{glossary}

## Output format: strict, and checked by a program

- One block per segment, in order, each beginning with its key alone on its own line, for
  example `[S012]`. Return all {segment_count} key(s); never merge or split segments.
- After the last segment you may add a line `[COMMENTARY]` followed by a few sentences on any
  choice the translator should review. Nothing else: no preamble, no code fences.

## Segments

{segments}
