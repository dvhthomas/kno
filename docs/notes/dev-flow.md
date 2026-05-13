# Developer flow — Kno

> Conventions for `dvhthomas/kno`. Augments [`AGENTS.md`](../../AGENTS.md). If anything here contradicts AGENTS.md, AGENTS.md wins.

---

## Branch model

Trunk-based on `main`. Branches named `<type>/<issue#>-<slug>` where type ∈ {feat, fix, chore, docs, refactor, ci, build, test}. Enforced by `.githooks/pre-push` + `.github/workflows/pr-validate.yml`.

PR-only merges to `main`; direct push blocked by branch protection.

---

## Labels

| Bucket | Examples | Managed by |
|---|---|---|
| **Type** | `enhancement`, `bug`, `documentation`, `chore` | `.github/labels.yml` (synced by `.github/workflows/labels.yml`) |
| **Lifecycle** | `shaping`, `in-progress`, `blocked`, `in-review`, `done` | [`dvhthomas/project-label-sync`](https://github.com/dvhthomas/project-label-sync) via `project-label-sync.yml` |
| **Area** | `area:web`, `area:auth`, `area:infra`, … | `.github/labels.yml` |
| **Status** | `blocked`, `wontfix`, `duplicate`, `release-blocker` | `.github/labels.yml` |

Don't apply lifecycle labels by hand — drag the card on [project 3](https://github.com/users/dvhthomas/projects/3) and the label syncs within 15 min. The board is canonical; sync is bidirectional.

---

## Project board transitions

Six columns: **Ideas → Shaping → In Progress → Blocked → In Review → Shipped**. Three close-states: **Shipped**, **Wontfix**, **Duplicate**.

Commands run from inside the kno checkout (`gh` infers `--repo`).

### Ideas (create issue)

```bash
gh issue create --title "feat: …" --body "…"
gh issue edit <n> --add-label enhancement  # type
gh issue edit <n> --add-label area:web     # area
```

### Ideas → Shaping

```bash
gh issue edit <n> --add-label shaping
git checkout -b <type>/<n>-<slug>
git commit --allow-empty -m "<type>(<area>): start shaping for #<n>"
git push -u origin HEAD
gh pr create --draft --base main --title "<type>: …" --body "Closes #<n>"
```

### Shaping → In Progress

```bash
gh issue edit <n> --remove-label shaping --add-label in-progress
```

Strict TDD from here per AGENTS.md.

### In Progress ↔ Blocked

```bash
# Blocked
gh issue comment <n> --body "Blocked on <reason>. Will resume when <condition>."
gh issue edit <n> --remove-label in-progress --add-label blocked

# Unblocked
gh issue edit <n> --remove-label blocked --add-label in-progress
```

### In Progress → In Review

Per AGENTS.md → Strict pre-merge review: run code-reviewer subagent against the PR's full diff vs. `main`, post findings as a PR comment, address Critical/Important.

```bash
gh pr comment <pr#> --body-file <findings.md>
gh pr ready <pr#>
gh issue edit <n> --remove-label in-progress --add-label in-review
```

### In Review → Shipped

```bash
gh pr merge <pr#> --squash --delete-branch
# Issue auto-closes via `Closes #<n>`; `done` label syncs within 15 min.
```

### In Review → deprioritized (issue stays open)

```bash
gh pr close <pr#> --comment "Deprioritized — see #<n>."
gh issue comment <n> --body "Deprioritized: <reason>."
gh issue edit <n> --remove-label in-review
# Drag the card back to Ideas on the board.
```

### Close as Wontfix or Duplicate

```bash
# Wontfix — comment MUST cite a PR, commit, or related issue
gh issue close <n> --reason "not planned" --comment "Wontfix — see PR #<m>."

# Duplicate — comment names the canonical issue
gh issue edit <n> --add-label duplicate
gh issue close <n> --reason "not planned" --comment "Duplicate of #<m>."
```

### Closing rule

Every issue close must cite a PR, commit, or related issue. Enforced by [`.github/workflows/enforce-issue-close.yml`](../../.github/workflows/enforce-issue-close.yml): detects auto-close via the GraphQL `ClosedEvent.closer` (PR merge or commit), or `#N`/SHA in the last 2 comments. Otherwise the workflow reopens with an explanation.

---

## Rule enforcement

| Layer | Mechanism | Bypass | Catches |
|---|---|---|---|
| Branch protection on `main` | repo setting | `--admin` only | direct push, force-push, branch delete |
| `.github/workflows/pr-validate.yml` | `pull_request` event | none | bad branch name, missing `Closes #N`, missing type/area labels |
| `.github/workflows/enforce-issue-close.yml` | `issues: closed` event | none | close without reference (reopens) |
| `.githooks/commit-msg` | client | `--no-verify` | non-conventional commit subject |
| `.githooks/pre-push` | client | `--no-verify` | bad branch name |
| Subagent review gates (see [`AGENTS.md`](../../AGENTS.md)) | agent discipline (Phase 1) | none gated yet — [#11](https://github.com/dvhthomas/kno/issues/11) tracks Phase 2 Action | logic, security, dead abstractions, missing edge cases |

If a rule needs to change, change the rule via PR — don't bypass.

---

## One-time setup (after `git clone`)

```bash
git config core.hooksPath .githooks
```

Repo-owner first-time setup also requires: [Projects v2 board](https://github.com/users/dvhthomas/projects), `project-label-sync.yml` → `project-url`, classic PAT with `project` + `public_repo` scopes ([create](https://github.com/settings/tokens/new?scopes=project,public_repo&description=kno-project-label-sync)) added as repo secret `PROJECT_PAT`, then trigger the label-sync workflow once.

---

## Flow data — `flowmetrics`

[`dvhthomas/flowmetrics`](https://github.com/dvhthomas/flowmetrics) reads cycle time, throughput, aging WIP, Monte Carlo forecasts from the GitHub API + the labels set by `project-label-sync`. Uses `GH_TOKEN` from `gh auth login`.

```bash
# Cycle time + throughput (P85, P95, IQR)
uv --directory ~/code/flowmetrics run flow cycle-time --repo dvhthomas/kno --since 30d

# WIP aging
uv --directory ~/code/flowmetrics run flow aging --repo dvhthomas/kno --workflow "in-progress,in-review"

# Monte Carlo forecast
uv --directory ~/code/flowmetrics run flow forecast when-done --repo dvhthomas/kno --items 5

# Composite JSON (agent-readable)
uv --directory ~/code/flowmetrics run flow report --repo dvhthomas/kno --since 30d --format json
```

No-clone alternative:

```bash
uvx --from git+https://github.com/dvhthomas/flowmetrics flow cycle-time --repo dvhthomas/kno --since 30d
```

---

## Quick lookups

```bash
gh issue list --label in-progress
gh issue list --label in-review
gh pr list --state open
gh issue list --label area:web --state open
gh issue view <n>
gh pr view <pr#>
```
