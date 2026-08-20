# Project Instructions

## Committing After Features

After completing a significant feature (not small fixes, edits, or exploratory work), run `uv run tc-commit` via the Bash tool and fill out the conventional commit prompts based on the work completed. Do this before reporting the task as done.

Always include a co-author footer in every commit:

```
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

When using non-interactive mode, pass it via `--footer`:

```bash
uv run tc-commit --type feat --subject "..." --footer "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" --yes
```
