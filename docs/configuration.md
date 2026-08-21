# Configuration

All configuration is via environment variables. Copy `.env.example` to `.env` and fill in the values you need.

The only truly required variable is an LLM API key.

---

## Minimal config

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

That's enough to run `theorycraft new` with the default model (`claude-sonnet-4-6`). Everything else is optional.

---

## Full reference

### LLM

| Variable | Default | Description |
|---|---|---|
| `THEORYCRAFT_MODEL` | `claude-sonnet-4-6` | Any [LiteLLM model string](https://docs.litellm.ai/docs/providers). Used for all nodes. |
| `ANTHROPIC_API_KEY` | — | Required for Claude models. |
| `OPENAI_API_KEY` | — | Required for OpenAI models (`gpt-4o`, etc.). |

**Model examples**

```bash
# Default — good balance of speed and quality
THEORYCRAFT_MODEL=claude-sonnet-4-6

# Deeper reasoning for complex products
THEORYCRAFT_MODEL=claude-opus-4-8

# OpenAI (requires OPENAI_API_KEY)
THEORYCRAFT_MODEL=gpt-4o

# Local via Ollama
THEORYCRAFT_MODEL=ollama/llama3
```

---

### GitHub

theorycraft can publish finished specs to GitHub. Two auth modes are supported.

#### PAT mode (simpler)

```bash
GITHUB_TOKEN=ghp_...
GITHUB_ORG=myorg      # optional — target org for new repos; uses your personal account if omitted
```

#### GitHub App mode (better for teams)

```bash
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=/path/to/private-key.pem
GITHUB_ORG=myorg
```

App auth takes precedence over PAT if both are set.

#### Archive repo

Automatically commits every finished spec into a GitHub repo:

```bash
THEORYCRAFT_ARCHIVE_REPO=coopdloop/theorycraft
```

Specs are committed to `sessions/<session-name>/product.json`. Useful for building a searchable history of generated specs.

---

### Slack bot (interactive)

Required to run `uv run tc-slack`.

```bash
SLACK_BOT_TOKEN=xoxb-...    # Bot User OAuth Token from OAuth & Permissions page
SLACK_APP_TOKEN=xapp-...    # App-level token from Basic Information → App-Level Tokens
```

See [slack.md](slack.md) for the full setup walkthrough.

---

### Notifications (outbound only)

These fire once when a spec is complete — they are one-way webhooks, not interactive.

```bash
# Slack incoming webhook
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../xxx

# Generic HTTP POST (receives a JSON payload with session name, output path, product name)
GENERIC_WEBHOOK_URL=https://myapp.com/webhooks/theorycraft
```

---

### Sessions and output

```bash
# Where SQLite checkpoint files live (one per session)
# Default: ~/.theorycraft/sessions/
THEORYCRAFT_SESSIONS_DIR=~/.theorycraft/sessions

# Default output directory for product.json files
# Default: current working directory
THEORYCRAFT_OUTPUT_DIR=~/specs
```

---

### Graph limits

```bash
# Max clarification rounds before forcing the agent into ideation
# Default: 2
THEORYCRAFT_MAX_CLARIFY_ROUNDS=2

# Max validate → revise cycles before forcing spec assembly
# Default: 3
THEORYCRAFT_MAX_REVISIONS=3
```

---

### Telemetry (Langfuse)

Optional. Traces every graph node as a Langfuse span.

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...

# Cloud (default)
LANGFUSE_HOST=https://cloud.langfuse.com

# Self-hosted
LANGFUSE_HOST=http://localhost:3000
```

---

## Complete .env example

```bash
# ── LLM ──────────────────────────────────────────────────────────────────
THEORYCRAFT_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...

# ── GitHub ────────────────────────────────────────────────────────────────
GITHUB_TOKEN=ghp_...
GITHUB_ORG=myorg
THEORYCRAFT_ARCHIVE_REPO=myorg/theorycraft

# ── Slack bot ─────────────────────────────────────────────────────────────
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...

# ── Notifications ─────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
GENERIC_WEBHOOK_URL=https://myapp.com/webhooks/theorycraft

# ── Sessions ──────────────────────────────────────────────────────────────
THEORYCRAFT_SESSIONS_DIR=~/.theorycraft/sessions
THEORYCRAFT_OUTPUT_DIR=~/specs

# ── Graph limits ──────────────────────────────────────────────────────────
THEORYCRAFT_MAX_CLARIFY_ROUNDS=2
THEORYCRAFT_MAX_REVISIONS=3

# ── Telemetry ─────────────────────────────────────────────────────────────
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```
