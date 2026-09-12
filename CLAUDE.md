# Project Instructions

## Committing After Features

After completing a significant feature (not small fixes, edits, or exploratory work), use `sc commit` via the Bash tool to create a conventional commit. Do this before reporting the task as done.

`sc` is the global `super-commit-cli` tool. Install it once with:
```bash
uv tool install git+https://github.com/coopdloop/super-commit-cli.git
```

Always include a footer crediting the acting model by name:

```
Agent assisted coded with: <model name>
```

Use the model actually running the task, read from the `PI_MODEL` environment
variable (e.g. `claude-opus-5` -> `Agent assisted coded with: claude-opus-5`).
Do not hardcode a model name.

When using non-interactive mode, pass it via `--footer`:

```bash
sc commit --type feat --subject "..." --footer "Agent assisted coded with: $PI_MODEL" --yes
```

To push separately after committing:

```bash
sc push
```
