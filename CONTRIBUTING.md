# Contributing

## Setup

```bash
uv sync                      # Python 3.12 and every dependency, dev tools included
uv run pre-commit install    # ruff, ruff-format and gitleaks on every commit
```

On a Dropbox-synced checkout, keep the virtualenv out of sync:
`xattr -w com.dropbox.ignored 1 .venv` (macOS).

## The gate

Every commit must pass:

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest
```

CI runs the same checks on every push and pull request, without API keys.

## Tests

| Directory | What |
|---|---|
| `tests/unit/` | One file per module. |
| `tests/integration/` | The MT pipeline end to end with a scripted `FakeProvider`, and the CLI through `typer`'s `CliRunner`. |
| `tests/ui/` | Streamlit pages through `streamlit.testing.v1.AppTest`. |
| `tests/fixtures/mini_project/` | A two-part project of invented Japanese sentences. |

Tests never call a paid API. Script model replies with `jtw.llm.fake.FakeProvider`; inject
it through `build_registry(config, factory)` in core tests, `obj={"provider_factory": ...}`
for the CLI, and `session_state["provider_factory"]` for the UI.

Coverage of `src/jtw` (excluding `ui/`, which the AppTest suite smoke-tests) must stay at or
above 85 %.

## Conventions

- Conventional Commits: `feat(scope):`, `fix:`, `test:`, `docs:`, `chore:`, `ci:`,
  `refactor:`. Imperative mood, subject at most 72 characters.
- Type hints everywhere (`mypy --strict`), no module-level side effects.
- Japanese-specific heuristics go in `src/jtw/text/ja.py` only.
- Model IDs come from `project.toml`, never from code.
- Update `docs/` in the same change that alters behaviour.

## Content

Never commit copyrighted text, machine-translation output, saves or logs. Everything under
`projects/` except `_template/` and `README.md` is ignored for that reason. Test fixtures use
short invented sentences and placeholder model IDs such as `fake-model-a`.
