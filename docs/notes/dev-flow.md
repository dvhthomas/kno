# Developer flow — Kno

> Conventions for everyday work on `dvhthomas/kno`. Augments the strict-TDD rule
> in [`AGENTS.md`](../../AGENTS.md). If something here contradicts AGENTS.md,
> AGENTS.md wins.

---

## Branch model

Trunk-based on `main`. Short-lived branches named `<type>/<issue#>-<slug>`:

```bash
git checkout -b feat/12-add-google-oauth
git checkout -b fix/47-config-leak
git checkout -b chore/3-bump-pydantic
git checkout -b docs/22-ops-manual
```

PR-only merges to `main`. No direct pushes once branch protection lands (Phase 2).

---

## PR-based flow

1. **Open or pick a GitHub issue.** Label it with type + area (the issue templates handle this).
2. **Branch:** `git checkout -b feat/<issue#>-<slug>`.
3. **Code via strict TDD** per [`AGENTS.md`](../../AGENTS.md). Multiple red→green commits in one PR is fine; each individual change still follows the cycle.
4. **Push, open PR with `Closes #<n>`.** CI (Phase 2 onward) runs `poe lint` + `poe typecheck` + `poe test`.
5. **Move the card on the Projects v2 board** to "In review" → `in-review` label auto-applied within 15 min (see [Labels](#labels)).
6. **Review, merge.** Closing the issue auto-moves the card to "Done" → `done` label applied.
7. **Deploy is automatic from `main`** once Phase 2 task 2.8 (CI deploy workflow) ships.

---

## Labels

Four buckets. Each managed by a different mechanism so authority is clear:

| Bucket | Examples | Managed by |
|---|---|---|
| **Type** | `bug`, `enhancement`, `documentation`, `chore` | `.github/labels.yml` → synced by `.github/workflows/labels.yml` on push to `main` |
| **Lifecycle** | `shaping`, `in-progress`, `blocked`, `in-review`, `done` | `dvhthomas/project-label-sync` via `project-label-sync.yml` — driven from the Projects v2 board, runs every 15 min |
| **Area** | `area:agent`, `area:auth`, `area:web`, … | `.github/labels.yml` |
| **Status flags** | `blocked`, `release-blocker`, `wontfix`, `duplicate`, `good first issue` | `.github/labels.yml` |

**The big rule: don't apply lifecycle labels by hand.** Drag the issue's card on the Projects v2 board and the label appears automatically. Hand-applying `in-progress` works (the sync is bidirectional) but the board is the canonical source.

## Project board: when can a card move?

Six columns on [project 3](https://github.com/users/dvhthomas/projects/3): **Ideas → Shaping → In progress → Blocked → In review → Shipped**. Each has a tiny **DoR** (must be true to *be* in this column) and **DoD** (must be true to *leave* it). Kept short on purpose — the columns are status, not gates.

| Column | DoR — to enter | DoD — to leave for the next column |
|---|---|---|
| **Ideas** | The idea exists. One line is fine. | You'd consider doing it; a `type:` label is applied. |
| **Shaping** | A type label is applied. | The card has enough description for someone (or an agent) to start cleanly: what + why + how you'd know it's done. |
| **In progress** | A branch exists (`<type>/<issue#>-<slug>`); first TDD red→green cycle landed. | A PR is open against `main` with `Closes #<n>`; CI is running. |
| **Blocked** | Work started but can't continue; a comment explains why. | Blocker resolved → back to **In progress**. |
| **In review** | PR open; CI green. | PR merged → **Shipped**. (Rejected? Move card back to **Ideas** with the rejection comment.) |
| **Shipped** | PR merged; issue auto-closed. | Terminal. |

**Why Shaping gets a label but Ideas doesn't.** Moving a card to Shaping means the work has been picked up — that starts the **lead time** clock (the `shaping` label's first-applied timestamp). **Cycle time** still doesn't start until **In progress** (the `in-progress` label). Ideas is the parking lot for things we haven't picked up; no clocks running.

**Anti-rule.** Don't add ceremony. If a card needs more thought, leave a comment; don't invent a longer DoR.

**For agents.** Before opening a PR, make sure the card is in **In progress** (move it there if not). After opening, leave it where it is — `project-label-sync` flips the label when a human drags the card to **In review**. If you find a card in the wrong column, just move it; don't ask.

### One-time setup before label sync works

This needs doing once when you first push the repo:

1. **Create a Projects v2 board** at https://github.com/users/dvhthomas/projects with the columns above (Ideas, Shaping, In progress, Blocked, In review, Shipped). *(Already done — [project 3](https://github.com/users/dvhthomas/projects/3).)*
2. **Update the project URL** in `project-label-sync.yml` → `project-url:`.
3. **Create a classic personal-access token** with `project` + `repo` scopes:
   https://github.com/settings/tokens/new?scopes=project,repo&description=kno-project-label-sync
4. **Add it as a repo secret named `PROJECT_PAT`** (Settings → Secrets and variables → Actions).
5. **Trigger the label-sync workflow once manually** in the Actions tab to verify config is good (leave `apply` unchecked for a preview run).

The `.github/workflows/labels.yml` workflow runs automatically on push and creates the type / area / status-flag labels listed in `.github/labels.yml`. No additional setup needed for that one.

---

## Flow data — checking the repo's health

`dvhthomas/flowmetrics` provides Vacanti-style metrics (cycle time p85, throughput, aging WIP, Monte Carlo forecasts) read straight from the GitHub API + the labels set by `project-label-sync`. Two invocation patterns from outside the flowmetrics checkout:

### Option A — clone once, use forever (recommended for repeated use)

```bash
git clone https://github.com/dvhthomas/flowmetrics ~/code/flowmetrics
cd ~/code/flowmetrics
uv sync
```

Then from anywhere:

```bash
# Cycle time + throughput (P85, P95, IQR)
uv --directory ~/code/flowmetrics run flow cycle-time \
  --repo dvhthomas/kno --since 30d

# WIP aging (what's currently in flight and how old)
uv --directory ~/code/flowmetrics run flow aging \
  --repo dvhthomas/kno --workflow "in-progress,in-review"

# Monte Carlo: when do the next N items ship?
uv --directory ~/code/flowmetrics run flow forecast when-done \
  --repo dvhthomas/kno --items 5

# Composite JSON envelope (the agent-readable shape)
uv --directory ~/code/flowmetrics run flow report \
  --repo dvhthomas/kno --since 30d --format json
```

### Option B — no clone, run on demand via `uvx`

```bash
uvx --from git+https://github.com/dvhthomas/flowmetrics flow cycle-time \
  --repo dvhthomas/kno --since 30d
```

Slower first time (downloads + builds in the cache); fast on subsequent runs.

### Option C — Flow Coach (once Phase 1 ships)

```bash
uv run kno serve
# then open the browser, sign in, pick `flow-coach`, ask "how is dvhthomas/kno doing?"
```

Same data, conversational. Available after Phase 1 Task 1.9 (flowmetrics MCP server).

Both flowmetrics paths use the `GH_TOKEN` env var that `gh auth login` sets up — no additional credential needed.

---

## Issue + PR state at a glance

Quick CLI lookups for "what's open":

```bash
# Everything currently in progress (per the board)
gh issue list --repo dvhthomas/kno --label in-progress

# Issues awaiting review
gh issue list --repo dvhthomas/kno --label in-review

# Open PRs
gh pr list --repo dvhthomas/kno --state open

# By area
gh issue list --repo dvhthomas/kno --label area:agent --state open

# Specific issue / PR
gh issue view 12
gh pr view 47
```

---

## Conventional commit prefixes

| Prefix | Category | When |
|---|---|---|
| `feat:` | feature | New user-visible behavior |
| `fix:` | bug | Bug fix |
| `docs:` | docs | Docs, README, ADR, comments |
| `refactor:` / `chore:` / `ci:` / `build:` | chore | No behavior change |

Examples (matching real commits in this repo):

```
feat(config): lenient Settings + providers_status (Task 0.2)
chore: project skeleton (Task 0.1) — monorepo layout, poethepoet, no Makefile
docs: purge Makefile references; poethepoet is the task runner
fix(api): /api/health returns 200 with not_configured when secrets absent
```

Body should explain the *why*. Test plan and acceptance per `AGENTS.md`.

---

## How AI coding agents fit in

`AGENTS.md` is the source of truth for the strict-TDD rule any AI assistant must follow when writing production code in this repo. This `dev-flow.md` is meta-process around it — branching, labels, flow data, commit prefixes — and is loaded as `[[../docs/notes/dev-flow.md]]` if an AI's context includes it.
