# Examples

Real-world walkthroughs of theorycraft sessions from start to finish.

---

## Example 1 — Simple CLI session

The fastest path: one command, one idea, one spec.

```bash
uv run theorycraft new "a CLI tool for hatching and tracking eggs"
```

```
╭──────────────────────────────────────────────────────────────────────╮
│ theorycraft  ·  collaborative product spec builder                   │
│ Session: cli-tool-for-hatching-and-tracking-eggs  ·  Model: claude-… │
╰──────────────────────────────────────────────────────────────────────╯

╭─ clarify (round 1 · question 1/3) ──────────────────────────────────╮
│ Who is the primary user — hobbyist chicken keepers, commercial farms, │
│ or biologists?                                                        │
╰──────────────────────────────────────────────────────────────────────╯
> hobbyist backyard chicken keepers

╭─ clarify (round 1 · question 2/3) ──────────────────────────────────╮
│ Should the tool track multiple clutches at once?                      │
╰──────────────────────────────────────────────────────────────────────╯
> yes, with named clutches

╭─ clarify (round 1 · question 3/3) ──────────────────────────────────╮
│ Any notification needs — alerts when hatch day is near?               │
╰──────────────────────────────────────────────────────────────────────╯
> yes, desktop notifications

╭─ theorycraft (round 1) ─────────────────────────────────────────────╮
│ EggWatch: a terminal-first egg incubation tracker                    │
│                                                                       │
│ A Go binary with embedded SQLite. Named clutches, hatch countdown,   │
│ temperature logging, and macOS/Linux desktop notifications via        │
│ go-notify. Single binary, no daemon.                                  │
│                                                                       │
│ What would you like to adjust? (Type /ready when happy)              │
╰──────────────────────────────────────────────────────────────────────╯
> add a candling log — record notes and viability per egg on specific days

╭─ theorycraft (round 2) ─────────────────────────────────────────────╮
│ EggWatch v2: adds a candling journal with per-egg notes and a        │
│ viability status (fertile / clear / quit / unknown)...               │
╰──────────────────────────────────────────────────────────────────────╯
> /ready

  Designing service_design...
  Designing architecture, api_design, database_design (parallel)...
  Designing frontend_design, sdk_design (parallel)...

╭─ review ────────────────────────────────────────────────────────────╮
│ services (1): eggwatch                                               │
│ api_routes (11)                                                      │
│ db_tables (4): clutches, eggs, candling_logs, notifications          │
│ frontend: TUI only (Bubble Tea)                                      │
│ sdk (1 client)                                                       │
│ adrs (3)                                                             │
╰──────────────────────────────────────────────────────────────────────╯
> approve

✓ Spec written to ./cli-tool-for-hatching-and-tracking-eggs/product.json (52.1 KB)
```

---

## Example 2 — Multi-round ideation and revision

Starting vague, steering through multiple rounds, revising after validation.

```bash
uv run theorycraft new
```

```
╭─ intake ────────────────────────────────────────────────────────────╮
│ What idea would you like to theorycraft today?                       │
╰──────────────────────────────────────────────────────────────────────╯
> something with AI and fitness

╭─ clarify (round 1) ─────────────────────────────────────────────────╮
│ 1. Who is the target user — casual exercisers, athletes, or trainers?│
│ 2. What's the core value — workout generation, tracking, or coaching?│
│ 3. Mobile app, web, or wearable integration?                         │
│ 4. Any existing tools to integrate with (Strava, Apple Health, etc.)?│
╰──────────────────────────────────────────────────────────────────────╯
> 1. intermediate runners training for a half marathon
> 2. adaptive training plans that adjust based on how the run actually felt
> 3. mobile-first progressive web app
> 4. Strava integration would be ideal

╭─ theorycraft (round 1) ─────────────────────────────────────────────╮
│ PaceWise: an adaptive half-marathon training coach                   │
│ ...                                                                  │
╰──────────────────────────────────────────────────────────────────────╯
> I want it to ask how the run felt on a 1-5 scale, not read from Strava.
> Keep it simple — no OAuth, just the runner logging manually.

╭─ theorycraft (round 2) ─────────────────────────────────────────────╮
│ PaceWise (simplified): manual effort logging, AI plan adjustment    │
│ ...                                                                  │
╰──────────────────────────────────────────────────────────────────────╯
> /ready

  [design nodes run]

╭─ review ───────────────────────────────────────────────────────────╮
│ services (2): api, planner                                          │
│ api_routes (14)                                                     │
│ db_tables (5): users, plans, runs, effort_logs, adjustments         │
│ frontend (6 pages)                                                  │
│ sdk (2 clients)                                                     │
╰────────────────────────────────────────────────────────────────────╯
> revise api_routes: add a /week/{n}/summary endpoint and a /plan/export as iCal

  Re-running api_design...

╭─ review (revision 1) ──────────────────────────────────────────────╮
│ api_routes (16)   ← 2 new routes added                              │
│ ...                                                                 │
╰────────────────────────────────────────────────────────────────────╯
> approve

✓ Spec written to ./something-with-ai-and-fitness/product.json
```

---

## Example 3 — Publishing to GitHub

Pass `--github repo` to automatically create a GitHub repo with the spec when you approve.

```bash
uv run theorycraft new "a link shortener with analytics" --github repo
```

After approval:

```
✓ Spec written to ./link-shortener-with-analytics/product.json (47.3 KB)
✓ GitHub: https://github.com/coopdloop/link-shortener-with-analytics-spec
```

The new repo will contain:
- `product.json` — the full spec
- `README.md` — auto-generated from the product vision

### Opening a PR instead

To add the spec to an existing repo as a pull request:

```bash
uv run theorycraft new "add user permissions layer" \
  --github pr \
  --github-repo myorg/myapp
```

This creates a branch `theorycraft/<session-name>` and opens a PR with `product.json`.

---

## Example 4 — Resuming after an interruption

If you close the terminal mid-session (or the process crashes), the session is fully checkpointed.

```bash
# See your sessions
uv run theorycraft list

# Resume exactly where you left off
uv run theorycraft resume pace-wise
```

```
Resuming session: pace-wise

╭─ theorycraft (round 2) ─────────────────────────────────────────────╮
│ [concept from before your terminal closed]                           │
│ What would you like to adjust? (Type /ready when happy)             │
╰──────────────────────────────────────────────────────────────────────╯
>
```

---

## Example 5 — Different models

```bash
# Faster, cheaper — good for quick ideation
THEORYCRAFT_MODEL=claude-haiku-4-5-20251001 uv run theorycraft new "a pomodoro timer"

# Deeper reasoning — better for complex enterprise products
THEORYCRAFT_MODEL=claude-opus-4-8 uv run theorycraft new "a multi-tenant SaaS billing platform"

# OpenAI
THEORYCRAFT_MODEL=gpt-4o uv run theorycraft new "a recipe recommendation engine"
```

---

## Example 6 — Slack session

After starting the bot (`uv run tc-slack`) and inviting it to a channel:

```
You:   @theorycraft a browser extension that blocks distracting sites during focus time

Bot:   ❓ Clarifying Questions — Round 1
       1. Should it work on a timer (Pomodoro-style) or on a manual toggle?
       2. Block list: preset categories, custom URLs, or both?
       3. Any sync needs — same blocklist across devices?
       4. Hard block or a friction nudge ("are you sure?")?

You:   1. Timer with configurable work/break lengths
       2. Both — presets plus custom
       3. Yes, sync via a lightweight account
       4. Hard block during work, nudge during breaks

Bot:   🧠 Theorycraft — Round 1
       FocusGuard: a Pomodoro-powered distraction blocker...
       [full concept]
       Reply with feedback, or type /ready

You:   /ready

Bot:   ⚙️ Designing...

Bot:   🔍 Review Spec
       services (2): api, extension-backend
       api_routes (12)
       db_tables (4)
       ...
       approve · revise <section>: <feedback> · restart

You:   approve

Bot:   ✅ Theorycraft Complete
       Spec: ~/.theorycraft/output/focusguard/product.json
       GitHub: https://github.com/coopdloop/focusguard-spec
```

---

## Example 7 — Non-interactive commit with tc-commit

After implementing a feature, commit without interactive prompts:

```bash
uv run tc-commit \
  --type feat \
  --subject "add candling log to eggwatch spec" \
  --scope graph \
  --files "theorycraft/graph/nodes/ideate.py,theorycraft/graph/state.py" \
  --footer "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" \
  --yes --push
```

```
✓ Staged 2 file(s).
╭── commit message preview ──╮
│ feat(graph): add candling  │
│ log to eggwatch spec       │
│                            │
│ Co-Authored-By: ...        │
╰────────────────────────────╯
✓ Committed a1b2c3d
✓ Pushed to origin/main
```
