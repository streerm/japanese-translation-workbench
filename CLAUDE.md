# Conventions for Claude Code in this repository

## Layout
- `src/jtw/` is the package; `jtw` is the console entry point (`src/jtw/cli.py`).
- The core (`model/`, `mt/`, `llm/`, `synth/`, `export/`, `text/`, `search.py`) is UI-free.
  `ui/` is a thin Streamlit layer and must not import `anthropic` or `openai`.
- All Japanese-specific regexes and heuristics live in `src/jtw/text/ja.py` and nowhere else.
- Every network call goes through `jtw.llm.registry`. Model IDs come from `project.toml`,
  never from code. API keys come only from the environment / `.env`.
- Per-work data lives under `projects/<slug>/` and is untracked, except `projects/_template/`.

## Gate (must be green before every commit)
```
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q
```

## Commits
- Conventional Commits (`feat(scope):`, `fix:`, `test:`, `docs:`, `chore:`, `ci:`, `refactor:`),
  imperative mood, subject at most 72 characters, body explains *why* when non-obvious.
- Tests ship with the code they cover.
- Update `docs/` in the same change that alters behaviour.

## Content rules
- Test fixtures use short, invented Japanese sentences and placeholder model IDs such as
  `fake-model-a`. Never commit real literary text, MT output, saves or logs.
- Never send a request to a paid API from tests; use `jtw.llm.fake.FakeProvider`.

## Style
- Python 3.12, full type hints (`mypy --strict`), ruff line length 100.
- Small functions, no module-level side effects, no global mutable state outside
  Streamlit session state.
