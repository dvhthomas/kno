# OQ-2 resolution: gh-velocity (and flowmetrics) integration

**Status:** Resolved 2026-05-12
**Spec refs:** spec §1 use cases · `docs/tasks.md` P0-pre.1 · Phase 1 tasks 1.9
**Related:** `docs/adr/0018-kno-lite-scope.md` (v1 scope)

---

## TL;DR

- **`gh-velocity` exists** at `github.com/dvhthomas/gh-velocity` (Dylan's project). It's a **`gh` CLI extension** in Go. Machine-readable output via `-r json`. Installed as `gh extension install dvhthomas/gh-velocity`. Latest release `v0.1.11`.
- **`dvhthomas/flowmetrics`** is Dylan's other project — created **today (2026-05-12)**. Python (`uv run flow ...`). Schema-versioned JSON envelope output (`--format json`). Has the forecasting + aging-WIP that gh-velocity doesn't.
- **Decision: ship two MCP servers** in v1's Phase 1: `gh_velocity` (current state metrics) and `flowmetrics` (forecasting + aging). Both are subprocess wrappers; both fit cleanly into `flow-coach`'s tool allowlist.

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
