# CLI Reference

theorycraft ships two executables: `theorycraft` (the agent) and `tc-commit` (conventional commit helper).

---

## theorycraft

### `theorycraft new`

Start a new session and generate a product spec.

```bash
uv run theorycraft new [IDEA] [OPTIONS]
```

| Option | Short | Description |
|---|---|---|
| `IDEA` | — | Product idea as a positional argument. If omitted, the agent will prompt you. |
| `--name` | `-n` | Session name. Auto-slugified from the idea if omitted. |
| `--output` | `-o` | Output directory for `product.json`. Default: `./<session-name>/`. |
| `--github` | — | Publish mode after spec is approved: `repo` (new repo), `pr` (PR on existing repo), `gist`. |
| `--github-repo` | — | Required for `--github pr`. Target repo as `org/repo`. |

**Examples**

```bash
# Minimal — idea as argument
uv run theorycraft new "a CLI tool for managing dotfiles"

# Custom session name and output dir
uv run theorycraft new "a habit tracker" --name habits --output ~/specs/habits

# Publish to a new GitHub repo when done
uv run theorycraft new "a task manager" --github repo

# Open a PR on an existing repo
uv run theorycraft new "add dark mode" --github pr --github-repo myorg/myapp

# No idea argument — agent will ask
uv run theorycraft new
```

#### How names are chosen

Two different names are produced during a run:

| Name | Source | Where it shows up |
|---|---|---|
| **Session name** | The idea prompt, with filler words (`i`, `want`, `to`, `build`, `a`…) dropped, slugified, and truncated to 48 characters **on a word boundary**. Override with `--name`. | `~/.theorycraft/sessions/<name>.db`, `./<name>/product.json`, `theorycraft resume <name>` |
| **Repo name** | The product name from the spec's `vision` section, falling back to the session slug. Suffix: `-spec`. | `github.com/<org>/<product>-spec` |

The repo name reserves room for its `-spec` suffix, so the suffix is never the
part that gets cut. GitHub caps repo names at 100 characters
(`theorycraft.naming.GITHUB_REPO_MAX_LENGTH`). If the repo name is already taken
by another repository on the account, theorycraft retries as
`<name>-spec-2`, `<name>-spec-3`, and so on.

So `"An LLM CLI chat where you talk with and I spec"` that names its product
*Paerhaps* publishes as `paerhaps-spec`, not as the whole truncated sentence.

---

### `theorycraft resume`

Resume an interrupted session. The session's state is fully checkpointed in SQLite, so you can close the terminal and come back later.

```bash
uv run theorycraft resume SESSION_NAME
```

**Example**

```bash
uv run theorycraft resume my-habit-tracker
```

theorycraft will re-raise the pending interrupt exactly where you left off — mid-clarification, mid-ideation, or mid-validation.

---

### `theorycraft list`

List all sessions with their last-modified time and size.

```bash
uv run theorycraft list
```

**Example output**

```
               Theorycraft Sessions
┌─────────────────────────┬──────────────────┬────────┐
│ Session                 │ Modified         │ Size   │
├─────────────────────────┼──────────────────┼────────┤
│ my-habit-tracker        │ 2026-08-21 10:23 │ 48.2 KB│
│ egg-hatcher-cli         │ 2026-08-20 16:49 │ 31.7 KB│
│ realtime-whiteboard     │ 2026-08-19 14:02 │ 52.1 KB│
└─────────────────────────┴──────────────────┴────────┘
```

Sessions are stored in `~/.theorycraft/sessions/` as SQLite files.

---

### `theorycraft show`

Pretty-print a completed product spec as a tree.

```bash
uv run theorycraft show SESSION_NAME [--spec PATH]
```

| Option | Description |
|---|---|
| `--spec`, `-s` | Path to `product.json`. Auto-detected from the default output location if omitted. |

**Example**

```bash
uv run theorycraft show my-habit-tracker
```

```
╭──────────────────────────────────────────────────────╮
│ HabitFlow                                            │
│ The frictionless habit tracker for developers        │
│                                                      │
│ Track streaks, get nudges, stay consistent...        │
╰──────────────────────────────────────────────────────╯
HabitFlow
├── services (2)
│   ├── go  api — Chi router
│   └── go  notifier — cron + push
├── api_routes (9)
│   ├── POST    /habits
│   ├── GET     /habits
│   ├── PATCH   /habits/{id}
│   └── ... 6 more
├── db_tables (4)
│   ├── users
│   ├── habits
│   ├── entries
│   └── streaks
├── frontend (5 pages)
│   ├── / — Dashboard
│   ├── /habits — Habit list
│   └── ...
├── sdk (2 clients)
└── adrs (3)
```

---

### `theorycraft slack`

Start the Slack bot in Socket Mode. Requires `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` in `.env`.

```bash
uv run theorycraft slack
# or equivalently:
uv run tc-slack
```

See [slack.md](slack.md) for full setup and usage.

---

## In-session commands

### During ideation

The agent presents a concept and waits for your response in the terminal.

| Input | Effect |
|---|---|
| Any free text | Agent incorporates your feedback and generates a refined concept |
| `/ready` | Accept the current concept and proceed to spec generation |
| `/clarify` | Go back to the clarifying questions phase |

**Example exchange**

```
> theorycraft (round 1)
  HabitFlow: a frictionless habit tracker...
  [full concept]
  What would you like to adjust?

> make the tech stack more minimal — no Kubernetes, just a single binary

> theorycraft (round 2)
  HabitFlow (v2): single Go binary with embedded SQLite...
  [refined concept]

> /ready
```

### During validation

The agent shows a summary of the generated spec and asks for approval.

| Input | Effect |
|---|---|
| `approve` | Write `product.json` and proceed to publish/notify |
| `revise <section>: <feedback>` | Re-run that design node with your feedback |
| `restart` | Discard the current design and return to ideation |

**Sections you can revise:** `api_routes`, `db_schema`, `frontend`, `sdk`, `architecture`, `services`

**Example**

```
> review spec
  services (2): api, notifier
  api_routes (9)
  db_tables (4): users, habits, entries, streaks
  frontend (5 pages)
  sdk (2 clients)

> revise api_routes: add pagination to all list endpoints and a /stats summary endpoint
```

---

## tc-commit

Interactive conventional commit CLI. Run it after completing a feature instead of `git commit` directly.

```bash
uv run tc-commit [OPTIONS]
```

### Interactive mode (default)

```bash
uv run tc-commit
```

Prompts you to:
1. Select files to stage
2. Choose commit type (`feat`, `fix`, `docs`, `refactor`, etc.)
3. Enter scope, subject, body, footer
4. Preview and confirm

### Non-interactive mode

Pass `--type` and `--subject` to skip all prompts:

```bash
uv run tc-commit \
  --type feat \
  --subject "add pagination to habit list endpoint" \
  --scope api \
  --body "Adds cursor-based pagination with a default page size of 20." \
  --footer "Closes #42" \
  --files "internal/api/habits.go,internal/api/habits_test.go" \
  --yes
```

| Option | Short | Description |
|---|---|---|
| `--type` | `-t` | Commit type: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `revert` |
| `--subject` | `-m` | Commit subject line (imperative, lowercase, no period, max 72 chars) |
| `--scope` | `-s` | Optional scope (module or area, e.g. `api`, `cli`, `graph`) |
| `--body` | — | Optional body paragraph |
| `--footer` | — | Optional footer (e.g. `Closes #42`, `Co-Authored-By: …`) |
| `--breaking` | — | Mark as a breaking change (adds `!` to type) |
| `--files` | `-f` | Comma-separated file paths or 1-based index numbers to stage |
| `--all` | `-a` | Stage all changed files |
| `--yes` | `-y` | Skip confirm and push prompts |
| `--push` | `-p` | Push to remote after committing |
| `--dry-run` | `-n` | Show what would happen without committing |

### Examples

```bash
# Stage specific files and commit non-interactively
uv run tc-commit --type fix --subject "handle nil pointer in clarify node" --files "theorycraft/graph/nodes/clarify.py" --yes

# Breaking change
uv run tc-commit --type feat --subject "replace session db path format" --breaking --yes

# Dry run to preview the commit message
uv run tc-commit --type docs --subject "update cli reference" --files "docs/cli.md" --dry-run

# Commit and push in one step
uv run tc-commit --type chore --subject "update dependencies" --all --yes --push
```
