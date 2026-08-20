# theorycraft

A LangGraph agent loop that collaboratively theory-crafts product ideas with you and outputs a **product-as-code** spec (`product.json`). Hand that spec to a coding agent and it can build the product.

## What it does

1. **Theory-crafts with you** — asks clarifying questions, expands your idea, lets you steer direction
2. **Designs the architecture** — Go/Python services, ADRs, tech choices
3. **Generates deterministic outputs** — OpenAPI 3.1 routes, SQLC-compatible PostgreSQL schemas, service specs
4. **Generates creative outputs** — React SPA component tree, TypeScript SDK interface
5. **Publishes** — writes `product.json`, optionally pushes to GitHub and sends Slack/webhook notifications
6. **Persists sessions** — interrupt and resume any session; run multiple products in parallel

## Install

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo>
cd theorycraft
cp .env.example .env        # fill in at minimum ANTHROPIC_API_KEY
uv sync
uv pip install -e .
```

## Quick start

```bash
# Start a new session (idea as argument)
uv run theorycraft new "a real-time team task manager"

# Or let the agent prompt you
uv run theorycraft new

# List sessions
uv run theorycraft list

# Resume an interrupted session
uv run theorycraft resume my-task-manager

# Pretty-print a completed spec
uv run theorycraft show my-task-manager
```

## Session flow

```
intake       → you describe the idea
clarify      → agent asks 3-4 clarifying questions (up to 2 rounds)
ideate       → collaborative theory-crafting loop; type /ready when done
─────────────────────────────────────────────────────────────────────
service_design → Go/Python service architecture
architecture   → ADRs and tech choices        ┐
api_design     → OpenAPI 3.1 routes           ├─ parallel
database_design→ SQLC PostgreSQL schemas      ┘
frontend_design→ React SPA pages/components   ┐ parallel
sdk_design     → TypeScript SDK interface     ┘
─────────────────────────────────────────────────────────────────────
validate     → review summary; approve / revise / restart
spec_compile → writes product.json
github_publish → (optional) new repo / PR / Gist
notify       → (optional) Slack + webhook
```

## CLI reference

```
theorycraft new [IDEA] [OPTIONS]
  --name, -n       Session name (auto-slugified from idea if omitted)
  --output, -o     Output directory (default: ./<session-name>/)
  --github         Publish mode: repo | pr | gist
  --github-repo    Existing repo for PR mode (org/repo)

theorycraft resume SESSION_NAME
theorycraft list
theorycraft show SESSION_NAME [--spec PATH]
```

### Ideation commands (during /ideate)

| Input | Effect |
|-------|--------|
| Free text | Agent incorporates feedback and responds |
| `/ready` | Proceed to architecture + spec generation |
| `/clarify` | Go back to clarifying questions |

### Validate commands (during /validate)

| Input | Effect |
|-------|--------|
| `approve` | Write product.json |
| `revise api_routes: add pagination` | Re-run api_design with feedback |
| `revise frontend: make it mobile-first` | Re-run frontend_design |
| `restart` | Return to ideation |

## Configuration

Copy `.env.example` to `.env`. Required: one provider API key (`ANTHROPIC_API_KEY` for the default model).

| Variable | Default | Purpose |
|---|---|---|
| `THEORYCRAFT_MODEL` | `claude-sonnet-4-6` | Any LiteLLM model string |
| `ANTHROPIC_API_KEY` | — | For Claude models |
| `LANGFUSE_PUBLIC_KEY` | — | Langfuse telemetry (optional) |
| `LANGFUSE_SECRET_KEY` | — | Langfuse telemetry (optional) |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Cloud or self-hosted |
| `GITHUB_TOKEN` | — | PAT for GitHub publishing |
| `GITHUB_APP_ID` + `GITHUB_APP_PRIVATE_KEY_PATH` | — | GitHub App auth (overrides PAT) |
| `GITHUB_ORG` | — | Target org for new repos |
| `SLACK_WEBHOOK_URL` | — | Slack incoming webhook |
| `GENERIC_WEBHOOK_URL` | — | POST to any URL on completion |
| `THEORYCRAFT_MAX_CLARIFY_ROUNDS` | `2` | Max clarification loops |
| `THEORYCRAFT_MAX_REVISIONS` | `3` | Max validate/revise loops |

## MCP servers

Copy `.theorycraft.json.example` to `.theorycraft.json` and configure MCP servers. They are started at session launch and their tools become available during ideation and architecture nodes.

```json
{
  "mcp_servers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/your/projects"]
    }
  }
}
```

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

## Development

```bash
uv run pytest tests/        # 11 tests
uv run pytest tests/ -v     # verbose
```

## Model choices

The default `claude-sonnet-4-6` works well for the full session. To use a different model:

```bash
THEORYCRAFT_MODEL=claude-opus-4-8 uv run theorycraft new "..."   # deeper reasoning
THEORYCRAFT_MODEL=gpt-4o uv run theorycraft new "..."             # needs OPENAI_API_KEY
```
