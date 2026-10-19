# Projects

Each work you translate is a *project*: a directory `projects/<slug>/` holding

| Path | What |
|---|---|
| `project.toml` | Title, author, MT columns and models, style notes, glossary, limits. |
| `source.json` | The source text split into parts and segments (written by `jtw ingest`). |
| `saves/` | One save per part plus rotating timestamped backups. |
| `logs/` | One JSON file per MT request. |
| `tmp/` | Deep Dive sessions. |
| `exports/` | Word documents. |

Everything in this directory is **ignored by git** except this README and `_template/`, so a
private work you add here never ends up in a commit. Create one with

```bash
jtw new my-work
jtw ingest my-work path/to/text.txt
```

Set `JTW_PROJECTS_DIR` to keep projects outside the repository altogether.
