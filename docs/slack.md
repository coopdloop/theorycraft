# Slack Bot

theorycraft ships a Slack bot that lets you run full theory-crafting sessions entirely from Slack. Every Slack thread maps to one persistent theorycraft session — interrupt it, come back tomorrow, and it picks up exactly where you left off.

---

## Prerequisites

- A Slack workspace where you have permission to install apps
- `ANTHROPIC_API_KEY` (or another LLM provider key) set in `.env`
- `GITHUB_TOKEN` set in `.env` if you want the bot to publish specs to GitHub

---

## 1. Create the Slack app

Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**.

### Enable Socket Mode

**Settings → Socket Mode** → toggle on. Generate an **app-level token** with the `connections:write` scope. Copy it — this is your `SLACK_APP_TOKEN` (`xapp-…`).

### Subscribe to events

**Features → Event Subscriptions** → toggle on, then under **Subscribe to bot events** add:

| Event | Why |
|---|---|
| `app_mention` | Starts or resumes a session when someone @mentions the bot |
| `message.channels` | Receives thread replies in public channels |
| `message.groups` | Receives thread replies in private channels |
| `message.im` | Receives direct messages |

### Add bot scopes

**Features → OAuth & Permissions → Scopes → Bot Token Scopes**:

| Scope | Why |
|---|---|
| `app_mentions:read` | Receive @mention events |
| `channels:history` | Read thread replies in public channels |
| `groups:history` | Read thread replies in private channels |
| `im:history` | Read direct messages |
| `chat:write` | Post messages and thread replies |

### Install to workspace

**Features → OAuth & Permissions** → **Install to Workspace**. Copy the **Bot User OAuth Token** (`xoxb-…`) — this is your `SLACK_BOT_TOKEN`.

---

## 2. Configure .env

```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...

# Optional: auto-commit every finished spec to a GitHub repo
THEORYCRAFT_ARCHIVE_REPO=your-org/theorycraft
```

---

## 3. Start the bot

```bash
uv run tc-slack
```

You should see:

```
[10:23:41] INFO  slack.app  Theorycraft Slack bot started as @theorycraft (U08...)
```

The bot connects over WebSocket (Socket Mode) — no public URL or reverse proxy needed.

---

## 4. Invite the bot to a channel

In Slack:
```
/invite @theorycraft
```

---

## 5. Start a session

@mention the bot with your idea:

```
@theorycraft a real-time collaborative whiteboard for remote teams
```

The bot creates a thread and the entire session lives there.

---

## Full session walkthrough

```
You:  @theorycraft a lightweight habit tracker for developers

Bot:  ❓ Clarifying Questions — Round 1
      1. Who is the primary user — solo devs or teams?
      2. Should it sync across devices or stay local?
      3. What's the most important metric to track — streaks, completion rate, or time spent?
      4. Any integration needs (GitHub commits, calendar, terminal)?

You:  1. Solo devs
      2. Local-first with optional sync
      3. Streaks
      4. Terminal is a must, GitHub would be great

Bot:  🧠 Theorycraft — Round 1
      HabitFlow: a terminal-first habit tracker...
      [full concept with name, stack, features]
      Reply with feedback, or type /ready to proceed.

You:  Drop the web frontend entirely, keep it 100% terminal. Go binary, embedded SQLite.

Bot:  🧠 Theorycraft — Round 2
      HabitFlow (minimal): a single Go binary with embedded SQLite...
      [refined concept]

You:  /ready

Bot:  ⚙️  Designing services…
      [parallel design nodes run — takes 30-90 seconds]

Bot:  🔍 Review Spec
      ┌─────────────────────────────┐
      │ services (1): habitflow     │
      │ api_routes (7)              │
      │ db_tables (3): habits,      │
      │   entries, streaks          │
      │ frontend: terminal TUI only │
      │ sdk (1 client)              │
      └─────────────────────────────┘
      • approve — write product.json
      • revise <section>: <feedback>
      • restart — go back to ideation

You:  revise api_routes: add a /export endpoint that dumps all data as JSON or CSV

Bot:  [re-runs api_design, posts updated review]

You:  approve

Bot:  ✅ Theorycraft Complete
      Spec: ~/.theorycraft/output/habitflow/product.json
      GitHub: https://github.com/your-org/habitflow-spec
```

---

## Commands reference (in-thread)

### During ideation

| Input | Effect |
|---|---|
| Free text | Agent refines the concept and responds |
| `/ready` | Proceed to spec generation |
| `/clarify` | Return to clarifying questions |

### During validation

| Input | Effect |
|---|---|
| `approve` | Write `product.json` and publish |
| `revise <section>: <feedback>` | Re-run that design node |
| `restart` | Return to ideation |

**Revisable sections:** `api_routes`, `db_schema`, `frontend`, `sdk`, `architecture`, `services`

---

## Session persistence

Each Slack thread maps to a SQLite checkpoint file in `~/.theorycraft/sessions/`. If the bot restarts mid-session:

1. The session checkpoint is intact
2. The next message in the thread resumes it automatically — no `/resume` needed

Sessions remain in `waiting` state between messages. The bot ignores concurrent messages to the same thread while a step is running.

---

## Archive to GitHub

Set `THEORYCRAFT_ARCHIVE_REPO` to automatically commit every completed spec into a GitHub repo:

```bash
THEORYCRAFT_ARCHIVE_REPO=coopdloop/theorycraft
```

Each spec is committed to `sessions/<session-name>/product.json` in that repo, building a gallery of all specs you've generated.

---

## Logging

The bot logs all activity to stdout with colored Rich output:

```
[10:23:55] INFO  slack.app      slack.mention  channel=C08...  text='a habit tracker'
[10:23:55] INFO  slack.app      slack.session  create  name=habit-tracker  id=a1b2...
[10:23:56] INFO  slack.adapter  [habit-tracker]  graph → running
[10:23:57] INFO  llm.router     simple  claude-sonnet-4-6  (2 msgs, temp=0.3)  'You are a...'
[10:23:59] INFO  llm.router     ←       847 chars  320 tok  '1. Who is the primary...'
[10:23:59] INFO  slack.adapter  [habit-tracker]  interrupt  type=clarify  round=1
[10:24:15] INFO  slack.adapter  [habit-tracker]  ← user  '1. solo devs, 2. local-first'
[10:24:15] INFO  slack.adapter  [habit-tracker]  graph → running
...
[10:25:30] INFO  slack.adapter  [habit-tracker]  complete  output=.../product.json
[10:25:31] INFO  integr.github  Committed 1 file(s) to coopdloop/theorycraft (bc1c62e)
```
