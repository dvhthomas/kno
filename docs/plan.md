# Kno — Implementation Plan

> **Source spec:** `docs/spec.md` v0.6 (commit `be3be7b`)
> **Status:** Phase 2 (Plan), draft v1
> **Last updated:** 2026-05-12
> **Companion:** `docs/tasks.md` — operational task list

---

## 1. Executive summary

Kno v1 ships in **7 phases (Phase 0 foundation + 6 vertical slices)**. Each post-Phase-0 phase ends with a demo that exercises one or more canonical workflows end-to-end. Total estimated calendar time: **8–12 focused weeks**, dependent on parallelism and OQ-resolution latency.

Headlines:

- **Vertical slicing over horizontal layers.** We ship Flow Coach end-to-end (UI → API → agent → tool → DB) in Phase 1 before adding KB sources in Phase 2 or panels in Phase 4. The first user-visible feature beats stack completeness.
- **Foundation is short.** Phase 0 is ~1 week and ends with a single `/api/health` route behind Google OAuth. We don't gold-plate substrate before there's product to validate it against.
- **Feedback loop is Phase 5, not "phase 8+1".** Per `feedback-refinement-is-v1`, the inspect→score→improve cycle ships before deploy.
- **Two users + deploy is Phase 6.** Until the system is feature-complete, multi-user isolation is asserted by tests rather than exercised by real second-user traffic.
- **9 ADRs surfaced from spec walkthroughs; 8 more identified during planning.** All listed in §9.

---

## 2. Slicing strategy: vertical over horizontal

The spec's architecture (§7) is layered (API → services → agent runtime → MCP/memory/KB). The temptation is to build each layer fully before the next: "finish all of `memory/`, then all of `mcp/`, then start on `agent/`." **We reject that.**

Each phase delivers a **runnable end-to-end slice** — one canonical user journey, observable, costed, testable — at the expense of completeness within any one layer. Concretely:

- Phase 1 ships *enough* of `memory/`, `mcp/`, `agent/`, `api/`, and `web/` to make Flow Coach work. Each module is intentionally minimal. The shape becomes load-bearing in Phase 2+ and is fleshed out then.
- Phase 2 ships *all* of `knowledge/` because the KB has clear internal cohesion and no value in halves. (Vertical doesn't mean "one feature at a time forever" — it means "always end with a working slice.")

**Why this matters here:** Kno's value depends on the feedback loop (§14). A horizontal-first plan would have the feedback loop arrive at the *end* of the calendar with zero data on which prompts are bad. Vertical slicing means by Phase 5 we already have weeks of real runs to feed `/admin/refine`.

---

## 3. Phase summary

| Phase | Vertical | Demo gate | Calendar |
|---|---|---|---|
| **0** | Foundation | `/api/health` behind Google login; pytest green; migrations clean | 1 week |
| **1** | Flow Coach end-to-end | "How is dvhthomas/kno doing?" → cited Vacanti answer via `/api/chat` and `/ui/chat` | 1.5 weeks |
| **2** | Knowledge Base + KB-QA | Ingest bitsby.me Hugo repo + one Drive folder; query both with correct citations | 2 weeks |
| **3** | Approval gates | A tool with `action_category: external_write` triggers UI pause; typed confirmation for `external_messaging` | 0.5 week |
| **4** | Panel of Experts + Co-planner | `program-review-panel` on a GitHub URL returns 5 attributed viewpoints + integrator synthesis | 2 weeks |
| **5** | Feedback loop | End-to-end: 👎 a run → `/admin/refine` proposes diff → approve → eval suite runs → new version active | 1.5 weeks |
| **6** | Multi-user + deploy | Deployed at `kno.fly.dev`; 2nd user invited; one week of real usage under $30 budget; flow-report weekly Action passes | 1.5 weeks |

**Total: ~10 weeks** with a single developer working focused hours. Faster with parallelism (see §6). Slower if OQs block — see §10.

---

## 4. Dependency graph

The big-picture dependency chain (each layer depends on everything above it):

```
                        ┌────────────────┐
                        │  Phase 0       │
                        │  Foundation    │
                        └────────┬───────┘
                                 │
                ┌────────────────┼────────────────┐
                ▼                                  ▼
        ┌──────────────┐                   ┌──────────────┐
        │  Phase 1     │                   │  Phase 2     │
        │  Flow Coach  │  ◄── KB-QA uses ──│  KB+KB-QA    │
        │              │      same chat    │              │
        │              │      runtime      │              │
        └──────┬───────┘                   └──────┬───────┘
               │                                   │
               ├───────────────┬───────────────────┤
               ▼               ▼                   ▼
        ┌──────────────┐  ┌───────────┐    ┌──────────────┐
        │  Phase 3     │  │ Phase 4   │    │   Phase 5    │
        │  Approval    │◄─┤  Panel +  │    │   Feedback   │
        │  gates       │  │ Co-planner│◄───┤   Loop       │
        │              │  │           │    │              │
        └──────┬───────┘  └─────┬─────┘    └──────┬───────┘
               │                │                  │
               └────────────────┼──────────────────┘
                                ▼
                        ┌──────────────┐
                        │  Phase 6     │
                        │  Multi-user  │
                        │  + Deploy    │
                        └──────────────┘
```

**Cross-phase coupling notes:**

- **Approval gates (P3) are a prerequisite for any external-write tool.** Phase 1/2/4 ship only `read`-category tools, so we can defer P3 without blocking flow coach or KB-QA. The first tool that needs an approval gate is in Phase 4 (panel may want `github_comment_issue` to leave summaries — though we'll keep the panel `read`-only in v1 to avoid this dependency).
- **Feedback loop (P5) needs real runs to demonstrate value.** It's safe to build the schema and CLI eval runner in Phase 5, but `/admin/refine` is best demonstrated against weeks of real usage from Phases 1–4. So we *implement* P5 before deploy (P6), but *evaluate its value* during P6's week-of-usage gate.

---

## 5. Phase-by-phase plan

### Phase 0 — Foundation

**Goal:** smallest possible runnable Python server with auth, DB, observability, and the empty shells of every major module. No agent, no chat, no KB.

**Deliverables:**

1. **Project skeleton**: `pyproject.toml` with all deps pinned per spec §4; `uv.lock`; `ruff` + `mypy --strict` + `pytest` configs; `pre-commit` hooks; `Makefile`.
2. **Config layer**: `kno.config` with pydantic-settings. Required env vars: `KNO_ADMIN_EMAIL`, `KNO_TOKEN_ENC_KEY`, `KNO_GOOGLE_CLIENT_ID`, `KNO_GOOGLE_CLIENT_SECRET`, `KNO_ANTHROPIC_API_KEY`, `KNO_OLLAMA_BASE_URL`, `DATABASE_URL`.
3. **Database schema (Alembic migration 0001)**: `users`, `sessions`, `service_connections`, `model_calls`, `runs`, `messages`, `tool_calls`, `audit_log`. Empty `agents`, `agent_versions`, `workflows`, `workflow_versions`, `skills`, `skill_versions` (populated in P1). SQLite WAL mode. SQLAlchemy 2.x async + base `UserScopedSession`.
4. **LangGraph base**: `agent.state.AgentState` TypedDict; `SqliteSaver` checkpointer wired; empty graph.
5. **LiteLLM client wrapper**: `kno.models.client.complete(model_alias, system, user, ...)` with model routing table (`router`, `synth`, `cheap_synth`); success callback writing `model_calls` rows.
6. **MCP host scaffolding**: `kno.mcp.host` with empty registry; `Connection` interface for tokens (decryption helpers ready but not used yet).
7. **Auth identity**: Google OAuth via `authlib`; session cookies (HMAC-signed, `HttpOnly`/`Secure`/`SameSite=Lax`); email allowlist loaded from `data/allowlist.txt`; `users` row upserted on first login; `/api/auth/login/google`, `/api/auth/login/google/callback`, `/api/auth/logout`.
8. **Web shell**: minimal HTMX-powered `/ui/login` page; redirect after login. Jinja2 templates with one base layout. No real chat UI yet.
9. **Health endpoint**: `GET /api/health` returns `{ok: true, version: <sha>, db: ok}` — requires no auth. `GET /api/me` returns current user — requires auth.
10. **Observability scaffold**: structured JSON logging via `structlog`; OpenTelemetry tracing wired but not yet exporting (Honeycomb env var optional).

**Verification (gates Phase 1):**
- `uv run kno-server` starts on :8000.
- `curl /api/health` returns 200 with `{ok: true}`.
- Open `/ui/login` in browser, log in via Google with an allowlisted email, see `/ui/` placeholder page.
- `uv run pytest tests/unit` passes (≥3 tests: config loading, encryption round-trip, allowlist parsing).
- `uv run alembic upgrade head` against a fresh SQLite file succeeds; schema matches expected tables.
- `uv run ruff check` + `uv run mypy src/kno` pass with zero errors.
- `pre-commit run --all-files` passes.

**ADRs to draft during this phase:** ADR-0001 (LiteLLM gateway), ADR-0002 (LangGraph as state machine), ADR-0010 (multi-user isolation enforcement), ADR-0011 (SQLite checkpointer co-located with app DB), ADR-0015 (KB substrate = sqlite-vec).

**Open questions to resolve before P1:** OQ-6 (initial invitees → `data/allowlist.txt` seed).

---

### Phase 1 — Flow Coach end-to-end

**Goal:** ship the canonical vertical. One user, one workflow, one agent, one tool. Browser UI works, run is captured, cost is on the ledger.

**Deliverables (numbered in dependency order; see `docs/tasks.md` for parallelism marks):**

1. **Skill loader + registry** (`kno.skills.loader`, `kno.skills.registry`): parse `data/skills/<slug>/SKILL.md` (frontmatter + body) into `SkillConfig`. Hot-reload via `POST /api/data/reload`.
2. **Agent loader + registry** (`kno.agents.*`): parse `data/agents/<slug>/{agent.yaml, persona.md}` into `AgentConfig`. Resolves `{{skill: name}}` includes at compile time.
3. **Workflow loader + registry** (`kno.workflows.*`): parse `data/workflows/<slug>/workflow.yaml` into `WorkflowConfig`. v1 supports `kind: chat` only.
4. **Working memory + virtual files** (`kno.memory.working`, `kno.agent.virtual_files`): in-context buffer + token accounting; messages >10k tok become virtual files with `load_file`/`peek_file` tool exposure. Larson 80%-window compaction at `compact` node.
5. **Semantic memory** (`kno.memory.semantic`): `semantic_facts(user_id, key, value)` reads/writes; `<user_facts>` block prepended to system prompt.
6. **LangGraph `chat` workflow runtime** (`kno.workflows.kinds.chat`): `router → retrieve → synth ↔ tools` graph. Router skipped when only one lane is plausible (single-agent chat).
7. **Per-run decrypted-token cache** (`kno.auth.tokens`): per-`run_id` in-memory cache for decrypted tokens; cleared on run end. ADR-0005.
8. **github MCP server** (`kno.mcp.servers.github`): wraps PyGithub or REST calls; tools: `github_search_issues`, `github_read_file`, `github_repo_summary`. All `action_category: read`.
9. **gh_velocity MCP server** (`kno.mcp.servers.ghvelocity`): wraps the `gh-velocity` CLI or library; tool: `gh_velocity_repo_metrics(repo, since)` returning Vacanti metrics. `action_category: read`. **Pre-req: OQ-2 resolved.**
10. **Seed data: skills, vacanti agent, flow-coach workflow** in `data.seed/`. Skills: `cite-sources`, `vacanti-metrics`, `flow-jargon`, `monte-carlo-explainer`. Agent: `vacanti`. Workflow: `flow-coach`.
11. **Chat service + API**: `kno.services.chat.run(user, workflow_slug, message)`; `POST /api/chat` SSE stream with `delta`/`tool_call`/`tool_result`/`run_complete`/`error` events.
12. **Chat UI**: `/ui/chat` page with workflow picker (just "Flow Coach" + "Default" in P1), HTMX SSE pane, message input. **Intentionally minimal** — no formatting beyond markdown rendering.
13. **Runs view (basic)**: `/ui/runs` lists runs for current user; `/ui/runs/<id>` shows timeline (model calls, tool calls, retrieved chunks). Read-only. Per-user filtering enforced.
14. **Anthropic prompt caching**: anthropic-direct path for `cache_control: ephemeral` on the system-prompt block. Block ordering per ADR-0004.

**Verification (gates Phase 2):**
- `POST /api/chat {workflow: "flow-coach", message: "How is dvhthomas/kno doing this month?"}` → SSE stream → final answer mentions cycle time, throughput, p85, with citation to `gh_velocity_repo_metrics`. Cost <$0.05 first call, <$0.02 subsequent.
- `/ui/chat` shows same conversation in browser.
- `/ui/runs/<id>` timeline shows: router call, synth call (tool_use), tool call, synth call (final), all with costs.
- Multi-user smoke: log in as a second allowlisted user, run same query → see different conversation; query `/api/runs` as user 1, do NOT see user 2's runs.
- Add a `data/workflows/test-noop/workflow.yaml` pointing at the default agent; `POST /api/data/reload` makes it appear in `/ui/chat` workflow picker without a server restart.

**ADRs to draft:** ADR-0004 (prompt cache block ordering), ADR-0005 (per-run token cache), ADR-0006 (semantic-fact bootstrap UX).

**OQ to resolve before P1 start:** OQ-2 (`gh-velocity` machine-readable output shape).

---

### Phase 2 — Knowledge Base + KB-QA

**Goal:** ingest user content from 4 source kinds; serve cited RAG answers via `kb-qa` workflow.

**Deliverables:**

1. **Migration 0002**: `kb_repos`, `kb_drive_folders`, `kb_docs`, `kb_chunks` (with `embedding` BLOB and `fts_text`), `kb_uploads`. sqlite-vec extension loaded; FTS5 virtual table created.
2. **Ollama embed client** (`kno.knowledge.embed`): batched embed via `nomic-embed-text` (768-dim) against `KNO_OLLAMA_BASE_URL`.
3. **Ingest base classes** (`kno.knowledge.sources.base`): `Source.fetch()`, `Source.extract()`, `Source.chunk()` abstract methods.
4. **Hugo source repo source** (`hugo_repo.py`): shallow `git clone` via `subprocess`; walk `content/`; parse frontmatter via `python-frontmatter`; heading-aware chunking via `markdown-it-py`. Citation = `repo@sha:path#L<n>-<m>`. **Primary source — most testing here.**
5. **Generic GitHub markdown source** (`github_repo.py`): same shape; walks any `.md` files.
6. **Google Drive folder source** (`gdrive.py`): `drive.readonly` + `spreadsheets.readonly` + `documents.readonly` scopes. Docs → export as md; Sheets → CSV → markdown table; PDFs → pypdf; plain `.md`/`.txt` direct. Per-file `modifiedTime` tracking. **Pre-req: Google connection with the new scopes in P0.**
7. **Direct upload source** (`upload.py`): `POST /api/kb/upload`; PDF via `pypdf`; MD via `markdown-it-py`; TXT direct. Content-addressed by SHA-256, stored under `data/kb/uploads/<user_id>/`.
8. **Retrieval** (`kno.knowledge.retrieve`): hybrid BM25 (FTS5) + vector (sqlite-vec) → RRF (k=60). Top-N=8.
9. **kb_search MCP server** (`kno.mcp.servers.kb_search`): `kb_search(query, k=8, source_kinds=null)` → chunks with citation refs. `action_category: read`.
10. **Seed: librarian agent + kb-qa workflow**. `librarian` uses `cite-sources` skill + a `kb-citation-format` skill. Workflow `kb-qa` allows only `mcp:kb_search`.
11. **KB UI** (`/ui/kb`): list ingested sources per user; "Sync now" / "Forget" buttons; drag-drop upload area; ingest status indicators.
12. **Optional KB-QA polish**: source filter on the query ("only bitsby.me"), formatted citations in chat output linking to GitHub URLs.

**Verification (gates Phase 3):**
- `kno-cli ingest hugo-repo dvhthomas/bitsby-me` → 100+ chunks indexed; visible in `/ui/kb`.
- `kno-cli ingest drive-folder <folder-id>` with a folder containing 1 Doc, 1 Sheet, 1 PDF, 1 `.md` → all 4 files ingested with correct mime handling.
- `POST /api/kb/upload` with a sample PDF → indexed; `/ui/kb` shows it with size + chunk count.
- `kb-qa` workflow returns a cited answer to "What did I write about evidence-based scheduling on bitsby.me?" — citation matches the original Hugo post's path + line range; clicking the citation opens the GitHub source view.
- Re-running `Sync now` after no source changes is a no-op (delta detection works).
- Multi-user isolation test: user 2 ingests different content; user 1's `kb-qa` doesn't surface user 2's chunks.

**ADRs to draft:** ADR-0015 confirmed (sqlite-vec viable at observed chunk counts).

**OQ to resolve before P2 start:** OQ-3 already resolved (A16 in spec).

---

### Phase 3 — Approval gates

**Goal:** make the side-effect approval model real. Build before any external-write tool exists so the gate is tested on synthetic cases first.

**Deliverables:**

1. **Migration 0003**: `action_approvals` table per spec §13.5.
2. **`action_category` declarations** in every existing MCP tool. P1/P2 tools should all already be `read` — verify and fail CI if any tool lacks a category declaration.
3. **policy.yaml loader** (`kno.services.policy`): parses `data/policy.yaml`; supports `defaults.categories`, `defaults.denied`, `per_user.<email>.require_typed_confirmation`. Lint enforces "category may only be upgraded, never downgraded."
4. **Approval gate in MCP host**: `kno.mcp.host.execute_tool` checks resolved category; if > `internal_write`, raises `interrupt_before` in LangGraph state with pending action snapshot.
5. **Approval API**: `GET /api/runs/pending` (current user's pending actions across all runs); `POST /api/runs/<id>/approvals/<action_id>` with `{decision: approve|deny|modify, modified_args?, typed_confirmation?}`; resumes graph via LangGraph `resume`.
6. **SSE events**: `pending_approval` event when graph pauses; `approval_resolved` event when user decides.
7. **Approval UI**: pending-action banner on `/ui/chat`; full preview with tool name, args, predicted effect; Approve / Deny / Modify buttons. Typed confirmation textbox for `external_messaging`; cooldown timer (5s) for `irreversible`.
8. **Audit log + admin view**: `/admin/approvals` shows aggregate decisions (admin only); per-run drill-down at `/ui/runs/<id>`. Decisions never deleted (DB constraint).
9. **CLI approval UX**: `kno-cli runs pending`; `kno-cli runs approve <run_id> <action_id>`; interactive `kno-cli chat` blocks on TTY with prompt. **OQ-12.**
10. **Synthetic test tool**: `mcp:test_approval` with declared categories `read`, `external_write`, `external_messaging`, `irreversible` — used by integration tests.

**Verification (gates Phase 4):**
- Integration test: agent calls `test_approval(category=external_write, ...)` → graph pauses → SSE emits pending_approval → `/api/runs/<id>/approvals/<action_id>` with approve → graph resumes → tool executes.
- Same for `external_messaging` with typed confirmation (request without the phrase is rejected by API).
- Same for `irreversible` with cooldown (request before 5s elapsed is rejected).
- Denial test: deny decision returns control to agent with a "denied by user" tool result; agent reasons about it.
- Audit log records all decisions with `decided_via` (`ui`/`cli`/`api`).
- Multi-user: user 1 cannot approve user 2's pending action.

**ADRs to draft:** ADR-0016 (LangGraph interrupt resume semantics on long timeouts).

**OQ to resolve before P3 start:** OQ-11 (initial policy.yaml content), OQ-12 (CLI approval UX).

---

### Phase 4 — Panel of Experts + Co-planner

**Goal:** ship the multi-agent panel pattern + the third canonical workflow.

**Deliverables:**

1. **Migration 0004**: `virtual_files` table (per-run shared content store).
2. **Panel runtime** (`kno.workflows.kinds.panel`): orchestrates artifact fetch + concurrent panelists + synthesizer per spec §9.4.
3. **Artifact fetcher** (`kno.workflows.kinds.panel.artifact`): GitHub URL → `github_fetch_repo_manifest` (new tool, see #5); Google Sheet URL → `gsheets_read_full`; result stored as virtual file. Size cap = 5000 tokens; depth-2 file-tree truncation. **ADR-0007.**
4. **Structured-output panelist node**: forces JSON via Anthropic tool_use mechanism; validates against pydantic `PanelistResponse {stance, key_points, evidence, questions}`; retries once on malformed.
5. **github MCP additions**: `github_fetch_repo_manifest(repo, depth=2, include_md=true, max_tokens=5000)`, `github_read_file(repo, path)`. Both `read`.
6. **google_drive MCP additions**: `gsheets_read_full(file_id, max_rows=500)` returning markdown table; `gdoc_read(file_id)` returning markdown. Both `read`.
7. **Seed: panelist agents** (5): `vacanti` (already P1), `shipping-pm`, `data-scientist`, `product-strategist`, `tech-architect`. Each with persona + appropriate skills.
8. **Seed: `integrator` agent** (synthesizer): persona = "synthesize a panel discussion with attribution."
9. **Seed: `program-review-panel` workflow**: `kind: panel`, agents list + synthesizer.
10. **Per-panelist SSE events**: `panelist_started`, `panelist_complete`, `panelist_failed` so UI can show progress.
11. **Per-panelist drill-down in `/ui/runs/<id>`**: parallel-track timeline for panels; each panelist's child-run linked.
12. **Partial-panel failure handling**: if a panelist fails twice, mark `failed` and continue; synthesizer notes the absence. **ADR-0008.**
13. **Tool-allowlist intersection UI** (`/ui/workflows/<slug>`): when configuring a panel, show effective tool set = workflow.allow ∩ agent.allowed. Warn on empty intersections. **ADR-0009.**
14. **calcmark MCP server** (`kno.mcp.servers.calcmark`): pending **OQ-1** resolution. v1 reads only.
15. **Seed: co-planner agent + workflow**: `kind: chat`, agent uses calcmark and kb_search tools.

**Verification (gates Phase 5):**
- `POST /api/chat {workflow: "program-review-panel", message: "Review this", input: {artifact_url: "https://github.com/dvhthomas/<test-repo>"}}` → SSE shows 5 `panelist_complete` events then synthesizer streams → final response attributes points to each panelist.
- `/ui/runs/<id>` for the panel run shows artifact fetch step + 5 parallel tracks + synthesizer; per-panelist click drills into their structured response.
- Force one panelist to fail (kill via test hook) → run completes; UI marks one panelist as failed; synthesizer answer notes the absence.
- Tool-allowlist intersection: configure a panel with an agent whose allowed tools don't overlap workflow tools → UI warning before save.
- Co-planner workflow: ask "Help me estimate this feature" → agent uses calcmark tool; response references calcmark structure.
- Cost: typical panel run < $0.20; warm-cache panel run < $0.15.

**ADRs to draft:** ADR-0007 (panel artifact size cap), ADR-0008 (partial-panel failure), ADR-0009 (tool-allowlist intersection).

**OQ to resolve before P4 start:** OQ-1 (calcmark API or scrape).

---

### Phase 5 — Feedback loop

**Goal:** inspect → score → improve loop is real and exercised against weeks of accumulated P1–P4 runs.

**Deliverables:**

1. **Migration 0005**: `run_feedback`, `eval_runs`, `eval_case_results`, `refine_proposals`.
2. **Feedback API + UI**: `POST /api/runs/<id>/feedback` and `POST /api/runs/<id>/messages/<mid>/feedback`. UI: 👍/👎 + optional comment under every message and at run level.
3. **Eval schema**: `data/evals/<workflow>/cases.yaml` with rubric fields (`must_include`, `must_call_tool`, `must_not_say`, `judge`, `max_cost_usd`).
4. **Eval runner**: `kno-cli eval <workflow>` runs every case against current version; LLM-as-judge using Haiku for rubric checks + a final natural-language judge prompt. Outputs pass/fail/cost table; persists to `eval_runs` + `eval_case_results`.
5. **Save-version UI with bump-level radio**: `patch`/`minor`/`major`. `patch` inherits prior eval record. Lint enforces ≥`minor` when diff touches `tools.*`, `agent:`, `agents:`, `model_override:`, `synthesizer:`, `*_schema:`. **OQ-14 → ADR-0013.**
6. **Auto-eval on save**: `minor` and `major` saves trigger eval run; UI blocks save until eval completes; diff view shows pass/fail delta vs. prior version.
7. **Refinement page** (`/admin/refine`): pick workflow + date range + 👎 filter → Claude proposes diff. Diff editor inline; "Save as v<n>" runs eval before commit.
8. **Refinement rate limit**: 1/workflow/user/UTC-day; admin `?force=true` override logged. **ADR-0014.**
9. **Refinement proposal storage**: every proposal persisted whether accepted or rejected, in `refine_proposals`.
10. **Eval seed cases**: 5–10 cases per shipped workflow (`flow-coach`, `kb-qa`, `co-planner`, `program-review-panel`) covering happy path + 1–2 known failure modes.

**Verification (gates Phase 6):**
- 👎 a Flow Coach run with a comment ("missed the WIP aging bit") → row in `run_feedback`.
- `kno-cli eval flow-coach` runs 5–10 cases against current `flow-coach@v1`, prints pass/fail with costs.
- Edit `flow-coach` persona in UI, mark as `minor`, click Save → eval auto-runs → diff view shows pass rate delta; save commits new version.
- Try to save a `tools.allow` change as `patch` → UI blocks with lint message.
- `/admin/refine` on `flow-coach` with last 14 days of 👎 → Claude proposes a prompt diff with rationale → approve → new version → eval runs → new version is active. Whole cycle <5 minutes wall time, <$0.30 cost.
- Second refinement attempt same day on same workflow → 429 with reset timestamp.

**ADRs to draft:** ADR-0013 (bump-level lint rules), ADR-0014 (refinement rate limit), ADR-0012 (version retention policy: full history).

**OQ to resolve before P5 start:** OQ-7 (retention — proposed: full history; sizes are tiny), OQ-14 (lint rules — proposed in spec; confirm).

---

### Phase 6 — Multi-user + deploy

**Goal:** Kno runs in production with a second invited user; budget caps enforced; weekly flow-report posts; success criteria pass.

**Deliverables:**

1. **Comprehensive multi-user isolation tests**: a dedicated test module that creates users A and B, has each ingest content + connect tokens + create private agents/workflows, then runs every API endpoint as A and asserts B's data is never returned. Same as B. Runs in CI.
2. **Invite flow**: admin-only `/admin/users` page; add email → updates `data/allowlist.txt` (committing if `KNO_DATA_GIT_REMOTE` is set). Sends a one-line welcome email via SMTP env config (or omits if no SMTP).
3. **Per-user budget caps**: enforced via `kno.agent.budget` against `model_calls`. Daily ($1, admin $2), monthly ($5, admin $30), per-session ($0.50, panels $2.00). Over-cap returns specific error to UI/CLI with reset time.
4. **Daily cost cron**: writes `metrics/cost-YYYY-MM-DD.json`; hard kill switch at $5/day total (configurable via env). **OQ-4.**
5. **/ui/connections page**: lists Google, GitHub, Slack, Notion, Granola providers with Connect/Revoke buttons. v1 wires Google + GitHub fully; the other three's Connect button opens OAuth and stores token but no MCP server uses them yet (forward-compat).
6. **Dockerfile + fly.toml**: multi-stage build (deps → app → final slim image). Fly volume for `data/`; Fly secrets for env vars. Region: closest to Dylan.
7. **Deploy workflow**: `.github/workflows/deploy.yml` runs on push to `main` after CI passes: `fly deploy`.
8. **Flow-report workflow**: `.github/workflows/flow-report.yml` Mondays 08:00 UTC; runs `gh-velocity` against `dvhthomas/kno` last 4 weeks; writes `metrics/flow-YYYY-WW.{json,md}`; opens/updates a tracking issue.
9. **Optional: git-backed data/**: implement `KNO_DATA_GIT_REMOTE` per spec §12.6. **OQ-9 → ADR-0017.** Lower priority — ship without if time pressure.
10. **README + ops doc**: how to deploy a fork; how to add a new MCP server; how to add a new OAuth provider. Single ops doc, no separate runbook.
11. **One-week real-usage validation**: I use Kno daily for a week. End-of-week review: cost ledger summary, top 5 surprising spends, top 5 prompt edits made via /admin/refine, multi-user isolation log review.

**Verification (gates v1 release):**
- All success criteria from spec §21 pass (15 items).
- Multi-user isolation CI test is green; the test does not pass at all if isolation is broken (no flakes — assertions are exact).
- Deploy succeeds; `kno.fly.dev` serves a login page; `/api/health` returns 200.
- One full week of normal use: total Anthropic spend < $10.
- Flow-report workflow has run successfully ≥ 2 weeks (validated post-release).

**ADRs to draft:** ADR-0017 (git-backed data sync semantics + conflict handling).

**OQ to resolve before P6 start:** OQ-4 (hard $ kill-switch number), OQ-6 (final invitees), OQ-9 (ship git-backed data or defer to v1.5?).

---

## 6. Parallelism map

Where two-developer (or pair-with-Claude) parallelism is safe:

| Phase | Parallel pair A | Parallel pair B |
|---|---|---|
| 0 | DB + migrations + UserScopedSession | Google OAuth + sessions + allowlist |
| 0 | LiteLLM client + ledger | MCP host scaffolding + Connection iface |
| 1 | Agent loader + workflow loader | github + gh_velocity MCP servers |
| 1 | `/api/chat` + SSE | `/ui/chat` + HTMX wiring |
| 2 | Hugo source ingest | Drive folder ingest (separate auth path) |
| 2 | GitHub markdown source | Direct upload source |
| 2 | KB UI | kb_search MCP server |
| 3 | policy.yaml loader + lint | Approval UI banner + SSE wiring |
| 4 | Panelist agent personas (5 — all pure config) | Panel runtime + virtual files |
| 4 | calcmark MCP | co-planner agent + workflow |
| 5 | Eval runner CLI | `/admin/refine` page + Claude diff proposal |
| 5 | Bump-level lint | Refinement rate limit |
| 6 | Connections UI | Fly deploy infra |

**Anti-parallelism warnings:**

- **Don't split `agent.graph` and `mcp.host` across people** — the interrupt-for-approval edge crosses both and races are nasty.
- **Don't parallelize within `services/`** if both branches touch the same service file; bias toward serialization for files with cross-cutting reads.
- **Don't parallelize migrations.** One migration per PR, serialize merges.

---

## 7. Verification checkpoints

Each phase's "Verification" section is a hard gate. Checkpoint flow:

```
Phase N work  →  Phase N verification battery  →  Commit verification record  →  Phase N+1 work
                          │
                          ▼
                if any check fails: STOP, fix in-phase, re-verify
```

Verification records live in `docs/verification/phase-<N>.md` — checked-in artifact noting date, who ran it, what passed, any deferred items.

**Hard rule: no phase-N+1 work begins until phase-N verification is fully green.** Loosely: if Phase 2 KB-QA isn't returning correct citations, do not start Phase 3 approval gates. The failure modes compound.

---

## 8. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LiteLLM `cache_control` underspec'd vs anthropic-direct | Med | Med | Anthropic-direct escape hatch in spec; tested in P1 |
| sqlite-vec performance under panelist concurrent reads | Low | Med | Each panelist reads independently; SQLite WAL handles concurrent readers fine. Verified in P4 |
| HTMX too thin for `/admin/refine` diff editor | Med | Low | SvelteKit fallback noted in spec; only needed if HTMX hits real limits |
| Prompt injection from Hugo repo content (a repo I control has malicious markdown) | Low | High | `<context>` wrapping per §17; tested in P2 with an injection-test fixture |
| Ollama unavailable on first request after deploy (slow first-call latency) | Med | Low | Pre-warm embedding model on container start; embed call has 10s timeout + fallback msg |
| Anthropic API rate limit during panel run (5 concurrent Sonnet calls) | Low | Med | LiteLLM retries; panel runtime catches rate-limit errors and serializes if multiple hits |
| Google OAuth flow breaks for trusted-tester users | Med | Med | Verify against ≥ 2 different Google accounts in P0; have a manual user-add backdoor for admin |
| Fly volume size grows past plan limit (KB cached repos) | Low | Med | KB repo cache periodically pruned; oldest commits GC'd; alert at 80% |
| Sub-OQ-1: calcmark.org has no extractable API → P4 co-planner blocked | Med | High | Fallback: ship co-planner without calcmark integration in P4; calcmark integration as v1.5 |

---

## 9. ADR list

ADRs live as separate files in `docs/adr/`. Drafted during the phase that surfaces them; merged with the spec on commit.

| # | Title | Phase | Status |
|---|---|---|---|
| **0001** | LiteLLM as model gateway | P0 | To-write |
| **0002** | LangGraph as agent state machine | P0 | To-write |
| **0003** | Shell-tool sandbox: subprocess + setrlimit + cwd jail (v1); Docker/Firecracker deferred | P0 (carries through) | To-write |
| **0004** | Prompt-cache block ordering | P1 | To-write |
| **0005** | Per-run decrypted-token cache | P1 | To-write |
| **0006** | Semantic-fact bootstrap UX (agent-asks-and-writes) | P1 | To-write |
| **0007** | Panel artifact fetch + size-cap strategy (manifest-only, 5k token cap, depth-2 truncation) | P4 | To-write |
| **0008** | Partial-panel failure semantics | P4 | To-write |
| **0009** | Agent × workflow tool-allowlist intersection — explicit UI, no silent drops | P4 | To-write |
| **0010** | Multi-user data isolation enforcement (UserScopedSession + dedicated CI test) | P0 (carries through to P6) | To-write |
| **0011** | SQLite checkpointer co-located with app DB (one `kno.db` file) | P0 | To-write |
| **0012** | Workflow/agent/skill version retention: full history | P5 | To-write |
| **0013** | Eval bump-level lint rules | P5 | To-write |
| **0014** | Refinement rate-limit (1/workflow/user/day) | P5 | To-write |
| **0015** | KB substrate = sqlite-vec for v1; Neon+pgvector migration path | P2 | To-write |
| **0016** | LangGraph interrupt resume semantics on long timeouts | P3 | To-write |
| **0017** | Git-backed data/ sync + conflict handling | P6 | To-write |

---

## 10. Open question resolution sequence

OQs from spec §3 with their resolution deadlines:

| OQ | Question | Resolve before | Default if unresolved |
|---|---|---|---|
| **OQ-1** | calcmark.org API or scrape? | P4 | Ship co-planner without calcmark tools; defer to v1.5 |
| **OQ-2** | gh-velocity machine-readable output? | **P1** | Block P1 start until resolved — 30-min spike before kickoff |
| **OQ-3** | Hugo from repo vs HTML | — | RESOLVED (A16 in spec) |
| **OQ-4** | Hard $ kill-switch number | P6 | $5/day (current spec default) |
| **OQ-5** | Shell-sandbox threat model | v2 | v1 ships subprocess+rlimit; OQ-5 informs v2 ADR |
| **OQ-6** | Initial invitees | P0 (allowlist seed) | Owner-only allowlist; add invitees as they're confirmed |
| **OQ-7** | Version retention | P5 | Full history (rows are small) |
| **OQ-8** | OAuth scopes per provider | P0 (Google, GitHub); P2+ for others | Documented in spec §12.2 |
| **OQ-9** | Git-backed data — v1 or v1.5? | P6 | Ship in v1 if Phase 6 has budget; otherwise v1.5 |
| **OQ-10** | Panel orchestration variant | — | RESOLVED (concurrent only in v1) |
| **OQ-11** | Initial policy.yaml content | **P3** | Pre-write before P3 start: `kno-cli policy lint` validates |
| **OQ-12** | CLI approval UX | P3 | Blocking prompt in TTY; fail-with-link otherwise |
| **OQ-13** | DSPy revisit triggers | v2 | Not blocking |
| **OQ-14** | Eval bump-level lint rules | P5 | Spec proposed list; confirm before P5 |

---

## 11. Cost-control checkpoints

Across phases, recurring cost checks:

- **End of each phase**: review last 7 days of `model_calls` ledger; flag any unexpected hot paths.
- **Before deploy (P6)**: confirm typical 5-hour session cost ≤ $1.20 (per the cost estimate exercise).
- **Post-deploy week 1**: daily review of `metrics/cost-YYYY-MM-DD.json`. Investigate any day > $2.

---

## 12. Glossary (plan-specific terms)

- **Phase**: a self-contained vertical slice ending with a demo gate.
- **Verification battery**: the set of automated + manual checks gating phase exit.
- **Vertical slice**: a deliverable that touches every layer needed for one user journey, even if each layer is minimal.
- **Lint rule (bump-level)**: schema-level constraint that forces a workflow/agent diff to be at least `minor` if it touches behavior-affecting fields.
- **Rate cap (refinement)**: per-workflow per-user per-UTC-day cap on `/admin/refine` invocations.
- **Demo gate**: the runnable scenario whose pass/fail decides whether a phase is complete.

---

## 13. After v1

Already-listed v1.5 / v2 items (from spec §22 + planning):

- Slack adapter (chat surface)
- Notion / Granola MCP tool servers
- Schedule + webhook workflow triggers
- Panel debate / round-robin variants
- Pipeline workflow kind
- Loop 4 dashboards
- DSPy as offline prompt-optimization tool
- Docker/Firecracker shell sandbox
- Automatic prompt rollback on eval regression
- Cross-workflow eval batteries
- Episodic memory retrieval
- HTTP crawler KB source
- `load_skills` lazy loading (if skill count justifies)

---

## 14. Change log

| Date | Author | Change |
|---|---|---|
| 2026-05-12 | Kno (drafted), Dylan (owner) | Initial v1 of plan based on spec v0.6 |
