# OQ-2 resolution: flowmetrics-primary for v1; gh-velocity deferred

**Status:** Resolved 2026-05-12 (updated same day after owner review)
**Spec refs:** spec §1 use cases · `docs/tasks.md` P0-pre.1, 1.9 · ADR-0018 (Kno-Lite v1 scope)

---

## TL;DR (current decision)

- **v1 ships ONE MCP server: `flowmetrics`** (`github.com/dvhthomas/flowmetrics`, Python, `uv run flow ...`, schema-versioned JSON envelope). It covers all four Vacanti metrics including P85 + Monte Carlo + aging WIP + flow efficiency + CFD.
- **gh-velocity is deferred from v1.** It works and is more mature, but for Kno-Lite the operational cost (extra `gh` CLI extension install, separate `project`-scope PAT, per-repo `.gh-velocity.yml` config, undocumented JSON schema) doesn't earn its place against a flowmetrics-only v1 that already serves `flow-coach`.
- **Tools split** in `tasks.md`: 1.9 → flowmetrics only; gh-velocity moved to the "deferred to v2" list.
- **Removed from `.env.example`**: `KNO_GH_VELOCITY_TOKEN`.

### Why flowmetrics-first

Trade-off matrix that drove the call:

| | flowmetrics | gh-velocity |
|---|---|---|
| Vacanti P85 | ✅ | ❌ (reports P90/P95) |
| Monte Carlo when-done / how-many | ✅ | ❌ |
| Aging WIP report | ✅ (explicit) | ⚠️ outlier detection only |
| Flow efficiency | ✅ | ❌ |
| CFD | ✅ | ❌ |
| Cycle time / throughput / WIP basics | ✅ | ✅ |
| Quality / release reports | ❌ | ✅ |
| Schema-versioned JSON | ✅ | ⚠️ undocumented |
| Language fit (Python) | ✅ | Go (subprocess only) |
| Operational complexity | low (`uv run flow`) | high (gh ext + PAT + .gh-velocity.yml) |
| Maturity | pre-alpha (created today) | v0.1.11 (~Jan 2026) |

The maturity gap is the main argument *for* gh-velocity. The Vacanti-essential gap (Monte Carlo + aging WIP) is the argument *against*. The owner judged flowmetrics is "marginally more useful for now" — meaning Vacanti essentials beat aggregate reports, even at pre-alpha. The decision is reversible: if flowmetrics churns badly or reveals gaps in 1–2 weeks of daily use, gh-velocity becomes the primary instead. Both projects are owned by Dylan, so the maturity risk is contained.

### When (and how) to revisit

Triggers to add gh-velocity back to v1 or to flip primary/secondary:

1. flowmetrics churns so fast that `tests/fixtures/flowmetrics_schema.json` invalidates weekly.
2. flowmetrics has a multi-week unfixed bug that gh-velocity wouldn't.
3. A new flow-coach use case demands gh-velocity's quality/release reports (out of v1 scope today).
4. gh-velocity becomes a Python library (currently CLI-only), removing the subprocess + extension-install cost.

Until one of those fires, flowmetrics is enough.

---

## Original research (kept for reference)

This file originally documented the two-server decision. The above supersedes it. The remainder of this document is the original gh-velocity research and the alternate two-server plan, kept so future-us can see what was considered.

## What gh-velocity reports

| Vacanti-style metric | gh-velocity coverage | Notes |
|---|---|---|
| Cycle time p50 (median) | ✅ | reports median |
| Cycle time **p85** | ⚠️ partial — reports median, mean, P90, P95 | **No P85**. Compute from raw if strict Vacanti needed (or accept P90 as close-enough; for flow-coach, accept and clearly label). |
| Throughput per period | ✅ | `flow throughput` subcommand |
| WIP count | ✅ | `status wip` — from Projects v2 board or labels |
| Aged WIP | ⚠️ partial — IQR-based outlier detection only | Use **flowmetrics** for explicit aging-WIP report |
| Monte Carlo (when-done / how-many) | ❌ | **Use flowmetrics** for this |
| Flow efficiency | ❌ | Use flowmetrics |
| Lead time | ✅ | `flow lead-time` |
| Quality / release | ✅ | `quality release` subcommand — bonus, not in core Vacanti |

## What flowmetrics adds (created today; pre-alpha)

- **Monte Carlo when-done** forecast (50 / 70 / 85 / 95 percentiles)
- **Monte Carlo how-many** forecast (items shipped by date)
- **Aging WIP** (explicit report)
- **Cumulative Flow Diagram** (CFD)
- **Flow efficiency** (Σ active / Σ cycle)
- **Schema-versioned JSON envelope** including chart data, captured logs, reproducer command — the exact shape an agent platform wants

## Integration plan for Kno

### Two MCP servers, not one

```
src/kno/mcp/servers/gh_velocity.py     # wraps `gh velocity ...`
src/kno/mcp/servers/flowmetrics.py     # wraps `uv run flow ...`
```

Both `action_category: read`. The `flow-coach` workflow's `tools.allow` lists both.

### Tool surface (proposed)

```python
# gh_velocity tools
gh_velocity_cycle_time(repo: str, since: str = "30d") -> CycleTimeStats
gh_velocity_throughput(repo: str, since: str = "30d", period: str = "week") -> ThroughputSeries
gh_velocity_wip(repo: str) -> WIPSnapshot
gh_velocity_report(repo: str, since: str = "30d") -> FullReport  # the report subcommand

# flowmetrics tools
flowmetrics_when_done(repo: str, items: int, since: str = "90d") -> ForecastWhenDone
flowmetrics_how_many(repo: str, by_date: str, since: str = "90d") -> ForecastHowMany
flowmetrics_aging_wip(repo: str) -> AgingWIPReport
flowmetrics_efficiency(repo: str, since: str = "90d") -> EfficiencyReport
```

### Invocation pattern

Both servers shell out to the binaries. Example for `gh_velocity_report`:

```python
proc = await asyncio.create_subprocess_exec(
    "gh", "velocity", "report",
    "-R", repo,
    "--since", since,
    "--config", config_path,
    "-r", "json",
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    env={
        **minimal_env,
        "GH_TOKEN": gh_token,
        "GH_VELOCITY_TOKEN": gh_velocity_token,
    },
)
stdout, stderr = await proc.communicate(timeout=60)
return parse_report(stdout)  # pydantic model from snapshotted JSON schema
```

### Authentication

- **`GH_TOKEN`**: standard GitHub PAT or OAuth token. Kno's existing GitHub connection (from §12 + ADR-0005 per-run token cache) supplies this.
- **`GH_VELOCITY_TOKEN`**: separate PAT with `project` scope, required for cycle time + WIP (because Projects v2 access). **Default `GITHUB_TOKEN` is insufficient.**
- **flowmetrics**: auth not documented in README; assume standard `GH_TOKEN` env var; needs empirical confirmation when wiring.

This means **`.env.example`** needs `KNO_GH_VELOCITY_TOKEN` as a separate var, *or* Kno's GitHub OAuth scope is extended to include `project` so a single token covers both. Recommended: **separate PAT** for v1 — simpler, doesn't require changes to the Google-style OAuth scope dance.

### Config file requirement

`gh-velocity` requires a `.gh-velocity.yml` in the repo root (or specified via `--config`). The `gh velocity config preflight` subcommand auto-generates one. Kno's MCP server:

1. On first call for a repo, run `gh velocity config preflight -R <repo>` to auto-generate a default config; cache the path in `kb_repos`-adjacent state.
2. Pass `--config <cached-path>` on subsequent calls.

### JSON schema discipline

gh-velocity's JSON schema is **not published in the README**. Action items:

1. **Snapshot the schema empirically** during Phase 1 P1-1.9 implementation. Run `gh velocity report -R dvhthomas/kno --since 30d -r json` and check the output into `tests/fixtures/gh_velocity_schema.json`.
2. **Pin `gh-velocity@v0.1.11`** in the Dockerfile's `gh extension install`.
3. CI test: assert the response shape matches the fixture on every upgrade.

flowmetrics describes itself as schema-versioned, which is friendlier — but it's pre-alpha (created today), so the same fixture-and-pin discipline applies.

## Risks and unknowns

- **gh-velocity JSON schema is undocumented** — must snapshot empirically; breaking changes between `0.1.x` releases are plausible at this maturity. **Pin exact versions.**
- **`gh` CLI is a system dependency.** Kno's Dockerfile must include the `gh` binary and run `gh extension install dvhthomas/gh-velocity@v0.1.11` at build time.
- **`.gh-velocity.yml` per-repo requirement** adds a step to the MCP call path. Mitigation: `config preflight` auto-generates a default; we cache it per-repo.
- **No P85 in gh-velocity output.** For strict Vacanti adherence, we'd need to recompute from raw cycle-time arrays — or pull `flowmetrics` (which does report P85/P95) for the forecasting tools and accept P90 as close-enough for daily reporting in `flow-coach`. Decision deferred to Phase 1 implementation; default = accept P90, document the gap in the Vacanti skill.
- **flowmetrics was created today (2026-05-12).** No releases. API will churn. Treat as Dylan-internal until tagged. Plan to pin a commit SHA, not a version.
- **flowmetrics auth story** is not in the README. Confirm before wiring.
- **`project` scope on GitHub PAT** is a new operational thing. Document in `docs/ops.md` under "first-time setup."

## Spec drift to address

The current spec calls for a single `gh_velocity` MCP server. The actual landscape calls for **two** (`gh_velocity` + `flowmetrics`). This is a minor spec adjustment:

- `docs/spec.md` §6 project structure: add `flowmetrics.py` alongside `gh_velocity.py` under `src/kno/mcp/servers/`.
- `docs/spec.md` §9 (workflows) + flow-coach example: tool allowlist updated to include both.
- `docs/tasks.md` Phase 1 task 1.9: split into 1.9a (`gh_velocity`) and 1.9b (`flowmetrics`), parallel-safe.
- `data.seed/workflows/flow-coach/workflow.yaml`: tool allowlist includes both.

To be applied as a small follow-up edit when Phase 1 starts.

## References

- [github.com/dvhthomas/gh-velocity](https://github.com/dvhthomas/gh-velocity)
- [gh-velocity.org](http://gh-velocity.org/)
- [gh-velocity v0.1.11 release](https://github.com/dvhthomas/gh-velocity/releases/tag/v0.1.11)
- [github.com/dvhthomas/flowmetrics](https://github.com/dvhthomas/flowmetrics)
- [flowmetrics docs site](https://dvhthomas.github.io/flowmetrics/)
- Daniel Vacanti, *Actionable Agile Metrics for Predictability*
