# Project Instructions

## Committing After Features

After completing a significant feature (not small fixes, edits, or exploratory work), use `sc commit` via the Bash tool to create a conventional commit. Do this before reporting the task as done.

`sc` is the global `super-commit-cli` tool. Install it once with:
```bash
uv tool install git+https://github.com/coopdloop/super-commit-cli.git
```

Always include a co-author footer in every commit:

```
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

When using non-interactive mode, pass it via `--footer`:

```bash
sc commit --type feat --subject "..." --footer "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" --yes
```

To push separately after committing:

```bash
sc push
```
