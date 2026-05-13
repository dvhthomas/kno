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

## Project board: how to move a card

Six columns on [project 3](https://github.com/users/dvhthomas/projects/3): **Ideas → Shaping → In progress → Blocked → In review → Shipped**.

`project-label-sync` is bidirectional — the `gh` commands below drive the entire flow without touching the board UI; the board moves to match within 15 minutes. (Or drag the card on the board; the labels follow.)

> Commands assume you're inside the kno checkout so `gh` infers the repo. Add `--repo dvhthomas/kno` if you're elsewhere.

### Create issue (lands in **Ideas**)

```bash
gh issue create --title "feat: …" --body "…"
gh issue edit <n> --add-label enhancement     # or: bug | documentation | chore
```

### **Ideas → Shaping** — work picked up; lead time starts; open the draft PR

```bash
gh issue edit <n> --add-label shaping

# Cut a branch + open a draft PR as the design-conversation vehicle
git checkout -b <type>/<n>-<slug>             # e.g. feat/12-google-signin
git commit --allow-empty -m "<type>(<area>): start shaping for #<n>"
git push -u origin HEAD
gh pr create --draft --base main \
    --title "<type>: …" --body "Closes #<n>"
```

First commits in Shaping can be design notes, a failing test, or an empty placeholder. Production code waits for **In progress** (strict TDD per [`AGENTS.md`](../../AGENTS.md)).

### **Shaping → In progress** — active work begins; cycle time starts

```bash
gh issue edit <n> --remove-label shaping --add-label in-progress
```

Strict TDD from here: red → green → refactor for every production code change. Push to the existing draft PR.

### **In progress → Blocked** — sideways step

```bash
gh issue comment <n> --body "Blocked on <reason>. Will resume when <condition>."
gh issue edit <n> --remove-label in-progress --add-label blocked
```

### **Blocked → In progress** — blocker resolved

```bash
gh issue edit <n> --remove-label blocked --add-label in-progress
```

### **In progress → In review** — mark PR ready for human review

```bash
gh pr ready <pr#>
gh issue edit <n> --remove-label in-progress --add-label in-review
```

### **In review → Shipped** — merge

```bash
gh pr merge <pr#> --squash --delete-branch
# Issue auto-closes via `Closes #<n>` in the PR body.
# `done` label arrives within 15 min via project-label-sync.
```

### **In review → rejected** — back to Ideas

```bash
gh issue comment <n> --body "Rejecting because <reason>."
gh pr close <pr#>
gh issue edit <n> --remove-label in-review
# Drag the card back to Ideas on the board.
```

**Rule of thumb.** The board is a status tool, not a gate. If a card is in the wrong column, move it; don't ask.

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
