# Contributing to Theorycraft

Thanks for your interest in contributing.

## Getting started

```bash
git clone <repo>
cd theorycraft
cp .env.example .env   # add ANTHROPIC_API_KEY at minimum
uv sync
uv pip install -e .
```

Run the tests before making changes to establish a baseline:

```bash
uv run pytest tests/ -v
```

## Workflow

1. Fork the repo and create a branch from `main`.
2. Make your changes.
3. Add or update tests for any new behavior.
4. Run `uv run pytest tests/` and confirm all tests pass.
5. Open a pull request — fill out the template.

## Commit style

This project uses [Conventional Commits](https://www.conventionalcommits.org/). You can use the interactive helper:

```bash
uv run tc-commit
```

Common types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`.

Breaking changes require a `!` after the type (e.g. `feat!: ...`) and a `BREAKING CHANGE:` footer.

## What to work on

Check open issues labeled `good first issue` or `help wanted`. For larger changes, open an issue first to align on approach before writing code.

## Code style

- Python 3.12+, formatted with `ruff`.
- Type annotations required for all public functions.
- Keep LangGraph node functions pure where possible — side effects belong in tool calls or publish nodes.

## Reporting issues

Use the issue templates. Include the theorycraft version (`uv run theorycraft --version`) and the relevant session log output.
