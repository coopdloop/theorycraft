# theorycraft

A LangGraph agent that collaboratively theory-crafts product ideas with you and outputs a **product-as-code** spec (`product.json`). Hand that spec to a coding agent and it can build the product.

```bash
uv run theorycraft new "a real-time collaborative whiteboard for remote teams"
```

---

## What it does

1. **Theory-crafts with you** — asks clarifying questions, expands your idea, lets you steer direction
2. **Designs the architecture** — Go/Python services, ADRs, technology choices
3. **Generates deterministic outputs** — OpenAPI 3.1 routes, SQLC-compatible PostgreSQL schemas, service specs
4. **Generates creative outputs** — React SPA component tree, TypeScript SDK interface
5. **Publishes** — writes `product.json`, optionally pushes to GitHub and sends notifications
6. **Persists sessions** — interrupt and resume any session; run multiple products in parallel
7. **Runs in Slack** — full interactive bot; every Slack thread is a persistent theorycraft session

## Ways to use it

| Mode | How |
|---|---|
| **CLI** | `uv run theorycraft new "your idea"` |
| **Slack bot** | `uv run tc-slack` — @mention the bot in any channel |

---

## Install

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/coopdloop/theorycraft
cd theorycraft
cp .env.example .env        # fill in ANTHROPIC_API_KEY at minimum
uv sync
uv pip install -e .
```

## Quick start

```bash
# Start a new session
uv run theorycraft new "a micro CLI tool for tracking daily habits"

# Let the agent prompt you for the idea
uv run theorycraft new

# List all sessions
uv run theorycraft list

# Resume an interrupted session
uv run theorycraft resume my-habit-tracker

# Pretty-print a completed spec
uv run theorycraft show my-habit-tracker
```

## Session flow

```
intake          → describe your idea
clarify         → agent asks 3-4 clarifying questions (up to 2 rounds)
ideate          → collaborative loop; steer the concept, type /ready when done
────────────────────────────────────────────────────────────────────────────
service_design  → define Go/Python services
architecture  ─┐
api_design    ─┤ parallel
database_design┘
frontend_design─┐ parallel
sdk_design    ─┘
────────────────────────────────────────────────────────────────────────────
validate        → review summary; approve / revise / restart
spec_compile    → writes product.json
github_publish  → (optional) new repo / PR / Gist
notify          → (optional) Slack + webhook
```

## CLI reference

```
theorycraft new [IDEA] [--name NAME] [--output DIR] [--github repo|pr|gist] [--github-repo ORG/REPO]
theorycraft resume SESSION_NAME
theorycraft list
theorycraft show SESSION_NAME [--spec PATH]
theorycraft slack
```

Full reference with examples: [docs/cli.md](docs/cli.md)

### Ideation commands

| Input | Effect |
|---|---|
| Free text | Agent incorporates feedback and responds |
| `/ready` | Proceed to spec generation |
| `/clarify` | Go back to clarifying questions |

### Validate commands

| Input | Effect |
|---|---|
| `approve` | Write product.json and publish |
| `revise api_routes: add pagination` | Re-run api_design with feedback |
| `revise frontend: make it mobile-first` | Re-run frontend_design |
| `restart` | Return to ideation |

## Slack bot

```bash
# Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN in .env, then:
uv run tc-slack
```

@mention the bot in a channel to start a session. Every Slack thread is a persistent theorycraft session — reply in the thread to drive the conversation, `/ready` to generate the spec.

Full setup guide: [docs/slack.md](docs/slack.md)

## Configuration

Copy `.env.example` to `.env`. Minimum required: `ANTHROPIC_API_KEY`.

| Variable | Default | Purpose |
|---|---|---|
| `THEORYCRAFT_MODEL` | `claude-sonnet-4-6` | Any LiteLLM model string |
| `ANTHROPIC_API_KEY` | — | For Claude models |
| `GITHUB_TOKEN` | — | PAT for GitHub publishing |
| `GITHUB_ORG` | — | Target org for new repos |
| `SLACK_BOT_TOKEN` | — | Slack bot token (`xoxb-…`) |
| `SLACK_APP_TOKEN` | — | Socket Mode token (`xapp-…`) |
| `SLACK_WEBHOOK_URL` | — | Outbound Slack notification |
| `THEORYCRAFT_ARCHIVE_REPO` | — | Repo to commit finished specs into |
| `THEORYCRAFT_MAX_CLARIFY_ROUNDS` | `2` | Max clarification loops |
| `THEORYCRAFT_MAX_REVISIONS` | `3` | Max validate/revise loops |

Full reference: [docs/configuration.md](docs/configuration.md)

## product.json structure

```
ProductSpec
├── vision          name, tagline, description, goals, target_users
├── services[]      name, language (go|python), framework, port, env_vars
├── api_routes[]    method, path, request/response JSON Schema, auth_required
├── db_schema       tables[] with columns, PKs, FKs, indexes + raw_sql
├── frontend        framework, pages[], shared_components[], design_notes
├── sdk             package_name, clients[] with typed TS method signatures
├── architecture    adrs[], tech_choices{}
└── infrastructure  deployment_target, required_env_vars, managed_services
```

## MCP servers

Configure external tools (filesystem, databases, APIs) that the agent can call during ideation and architecture nodes.

```json
// .theorycraft.json
{
  "mcp_servers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/your/projects"]
    }
  }
}
```

## Development

```bash
uv run pytest tests/        # run all tests
uv run pytest tests/ -v     # verbose

uv run tc-commit            # interactive conventional commit
uv run tc-commit --type feat --subject "..." --yes   # non-interactive
```

See [docs/examples.md](docs/examples.md) for real session walkthroughs.

## Model choices

The default `claude-sonnet-4-6` works well for the full session.

```bash
THEORYCRAFT_MODEL=claude-opus-4-8 uv run theorycraft new "..."   # deeper reasoning
THEORYCRAFT_MODEL=gpt-4o uv run theorycraft new "..."             # needs OPENAI_API_KEY
```
