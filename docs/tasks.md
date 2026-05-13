# Kno-Lite — Task List

> **Source plan:** `docs/plan.md` v2 (Kno-Lite scope per ADR-0018)
> **Source spec:** `docs/spec.md` v0.9 (full design vision; v1 scope per ADR-0018)
> **Status:** Phase 3 (Tasks), v2 (post-ADR-0018 rewrite)
> **Last updated:** 2026-05-12

Conventions:
- `[ ]` open · `[x]` done · `[~]` in progress · `[-]` cancelled · `[v2]` deferred
- Tags: **[P]** parallel-safe · **[B]** blocking · **[F]** fast (<2h) · **[S]** slow (>1d)
- Each task: **Acceptance** = what must be true · **Verify** = how to confirm · **Files** = surface area
- **Tasks within a phase honor the order listed unless [P]-marked.**

---

## Pre-flight (target: 2–3 days)

- [x] **P0-pre.1**: Resolve OQ-2 (gh-velocity output shape). **[B][F]** — **Resolved 2026-05-12.**
  - Resolution: `docs/notes/gh-velocity.md` (current section). **v1 ships flowmetrics only**; gh-velocity deferred. flowmetrics covers all four Vacanti metrics + Monte Carlo + aging WIP + flow efficiency + CFD, with a schema-versioned JSON envelope. Drops three operational costs from Phase 1 (`gh` CLI extension install, separate `project`-scope PAT, per-repo `.gh-velocity.yml` config).

- [ ] **P0-pre.2**: Dev environment up. **[B][F]**
  - Acceptance: Python 3.12 via `uv`; Ollama with `nomic-embed-text` + `llama3.1:8b` (or `:70b` if RAM allows); `.env` populated.
  - Verify: `uv python list` shows 3.12; `curl http://localhost:11434/api/tags` lists both Ollama models; `.env` validates against `.env.example`.

- [ ] **P0-pre.3**: Provision credentials. **[B][F]**
  - Acceptance: Anthropic API key with budget visible; Google OAuth client (Web app, `http://localhost:8000/api/auth/google/callback` authorized); GitHub OAuth app with `repo` scope.
  - Verify: `curl -H "x-api-key: $KNO_ANTHROPIC_API_KEY" https://api.anthropic.com/v1/models` returns 200; OAuth flows complete to a placeholder callback.

- [ ] **P0-pre.4**: Draft initial skills. **[F]**
  - Acceptance: 5 skill markdown files under `data.seed/skills/{cite-sources, vacanti-metrics, flow-jargon, monte-carlo-explainer, cost-aware-reasoning}/SKILL.md` with proper frontmatter.
  - Verify: each loads as valid YAML frontmatter + non-empty body; total content < 5k tokens each.

---

## Phase 0 — Foundation + Chat (target: 2 weeks)

### 0.1 Project skeleton **[B][F]**
- Acceptance: `pyproject.toml` with pinned deps (`fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`, `pydantic-settings`, `sqlalchemy`, `aiosqlite`, `alembic`, `litellm`, `langgraph`, `langgraph-checkpoint-sqlite`, `anthropic`, `ollama`, `authlib`, `cryptography`, `mcp`, `python-frontmatter`, `markdown-it-py`, `jinja2`, `typer`, `structlog`); `uv.lock`; ruff + mypy --strict + pytest + pre-commit; Makefile with `dev` `test` `lint` `mypy` `migrate` `serve`.
- Verify: `uv sync` clean venv; `make lint` passes; `pre-commit install` succeeds; `make test` runs 0 tests OK.
- Files: `pyproject.toml`, `uv.lock`, `.pre-commit-config.yaml`, `Makefile`, `tests/conftest.py`.

### 0.2 Config layer **[F]** *Depends on 0.1*
- Acceptance: `kno.config.Settings` (pydantic-settings) loads required env vars; fail-fast on missing.
- Verify: unit test: missing `KNO_ANTHROPIC_API_KEY` raises `ConfigError` naming the key; `.env.example` documents every var.
- Files: `src/kno/config.py`, `.env.example`, `tests/unit/test_config.py`.

### 0.3 DB + migration 0001 **[B][P with 0.4]** *Depends on 0.2*
- Acceptance: Alembic configured against SQLite; migration 0001 creates `users`, `sessions`, `service_connections`, `model_calls`, `runs`, `messages`, `tool_calls`, `audit_log`, `semantic_facts`, `agents`/`agent_versions` (empty shells reserved for v2), `workflows`/`workflow_versions`, `skills`/`skill_versions`. WAL pragmas applied on connect.
- **`service_connections` schema must include `connection_kind` (TEXT: `oauth`/`api_token`/`none`) and `config_json_enc` (BLOB, nullable) columns** per **ADR-0019**. v1 only exercises `oauth`; the columns ship from day one so v2 API-token integrations (Jira, Linear) don't require a future migration.
- Verify: `alembic upgrade head` clean; `alembic downgrade base` then `upgrade head` round-trips; `PRAGMA journal_mode` returns `wal`; schema test asserts the two new columns exist on `service_connections`.
- Files: `alembic.ini`, `migrations/env.py`, `migrations/versions/0001_*.py`, `src/kno/db/{session.py, models.py}`.

### 0.4 Google OAuth + sessions **[P with 0.3]**
- Acceptance: `authlib` Google OAuth at `/api/auth/google/login` + `/api/auth/google/callback`; HMAC-signed session cookies (`HttpOnly`, `Secure`, `SameSite=Lax`, 30d rolling); `users` row upserted; **no allowlist enforcement** beyond `KNO_ADMIN_EMAIL` matching (single-user scope per ADR-0018).
- Verify: log in via Google with `KNO_ADMIN_EMAIL` → redirected to `/ui/`; second visit reuses session; logout clears.
- Files: `src/kno/auth/{sessions.py, providers/google.py}`, `src/kno/api/auth.py`.

### 0.5 UserScopedSession wrapper (v1: smoke-test only) **[B]** *Depends on 0.3*
- Acceptance: `UserScopedSession` wraps `AsyncSession`; injects `user_id` filter on `SCOPED_TABLES`; ships even at single-user scope (per ADR-0018: build the muscle, defer the full CI battery). **Multi-user CI isolation test deferred to v2.**
- Verify: unit test with two synthetic users; user A's `runs` query never returns user B's row.
- Files: `src/kno/db/session.py` (extension), `tests/unit/test_user_scoped_session.py`.

### 0.6 LiteLLM client + ledger **[P with 0.7]** *Depends on 0.2, 0.3*
- Acceptance: `kno.models.client.complete(alias, ...)` wraps `litellm.acompletion`; routing aliases (`router=haiku`, `synth=sonnet`, `cheap_synth=haiku`, `eval_judge=haiku`). Success callback writes `model_calls` row. Ollama fallback configured for `synth` (`ollama/llama3.1:8b` or `:70b`).
- Verify: integration test with mocked `acompletion` writes a ledger row; callback shape stable.
- Files: `src/kno/models/{client.py, routing.py, ledger.py}`, `tests/integration/test_ledger.py`.

### 0.7 MCP host scaffolding **[P with 0.6]** *Depends on 0.3*
- Acceptance: `kno.mcp.host` with empty registry; `ToolDescriptor` carries `action_category`; `Connection` interface for token vault access.
- Verify: unit test: register no tools; `host.list_tools()` empty; `host.execute_tool('missing')` raises.
- Files: `src/kno/mcp/{host.py, registry.py}`, `tests/unit/test_mcp_host.py`.

### 0.8 LangGraph base + AgentState with `budget_remaining_usd` **[P with 0.7]** *Depends on 0.3*
- Acceptance: `AgentState` TypedDict with `messages`, `workflow_slug`, `workflow_version_id`, `user_id`, `run_id`, `budget_remaining_usd` (per ADR-0018 item 10), `retrieved_chunks`, `virtual_files`. `AsyncSqliteSaver` wired to `data/kno.db` (per ADR-0011).
- Verify: smoke test: 2-node graph increments counter; persists across process restart via checkpointer.
- Files: `src/kno/agent/{state.py, checkpointer.py}`, `tests/unit/test_checkpointer.py`.

### 0.9 Token vault with envelope encryption **[F]** *Depends on 0.3*
- Acceptance: `kno.auth.tokens` Fernet-encrypts at the column level using `KNO_TOKEN_ENC_KEY` (the KEK). Per-row encryption supports future rotation; documented in `docs/ops.md` skeleton.
- Verify: round-trip test; wrong-key test fails clearly.
- Files: `src/kno/auth/tokens.py`, `tests/unit/test_tokens.py`, `docs/ops.md` (initial draft).

### 0.10 Per-run token cache **[F]** *Depends on 0.9*
- Acceptance: `get_or_decrypt(run_id, provider)` caches in-process per run; cleared at run end. ADR-0005.
- Verify: integration test: two tool calls in one run → 1 decrypt; new run → fresh decrypt.
- Files: `src/kno/auth/tokens.py` (extension).

### 0.11 Skill loader **[B][P with 0.12]** *Depends on 0.3*
- Acceptance: parse `data/skills/<slug>/SKILL.md` (frontmatter + body) into `SkillConfig`; in-memory registry; hot-reload via `POST /api/data/reload`.
- Verify: unit test loads `cite-sources` fixture; retrieves by slug; reload picks up an edit.
- Files: `src/kno/skills/{loader.py, schema.py, registry.py}`.

### 0.12 Workflow loader (kind: chat; persona inline; no Agent layer) **[B]** *Depends on 0.11*
- Acceptance: parse `data/workflows/<slug>/workflow.yaml` into `WorkflowConfig`; persona is a `persona: persona.md` reference inline (no separate Agent primitive per ADR-0018); validates `kind: chat`; resolves skill includes. Schema includes optional `tools.connections: {provider: [labels]}` block per ADR-0019 §2.5 (per-workflow connection ticks).
- Verify: unit test loads `default` workflow; persona content + skills properly inlined; `tools.connections` parses when present and defaults to "all user's connections for provider" when absent.
- Files: `src/kno/workflows/{loader.py, schema.py, registry.py, kinds/chat.py}`.

### 0.13 Working memory + virtual files + 80% compaction **[P with 0.14]**
- Acceptance: token accounting per message; messages >10k tokens stored as `virtual_files` row (added in migration 0001 reserved table or new migration); `load_file`/`peek_file`/`extract_file` MCP tools (`read`); compact node at 80% window.
- Verify: synthetic test: feed 50 messages × 1k tokens; compaction fires; virtual file created.
- Files: `src/kno/memory/working.py`, `src/kno/agent/{virtual_files.py, nodes/compact.py}`, `src/kno/mcp/servers/virtual_files.py`.

### 0.14 Semantic memory + `remember_fact` tool **[P with 0.13]** *Depends on 0.3*
- Acceptance: `semantic_facts` reads/writes; `<user_facts>` block prepended to system prompt; `remember_fact(key, value)` MCP tool `action_category: internal_write` (auto-allowed in UI sessions); `/ui/facts` shows + allows edits.
- Verify: integration test: agent calls `remember_fact("name", "Dylan")`; fact appears on next turn's `<user_facts>` block; `/ui/facts` lists it.
- Files: `src/kno/memory/semantic.py`, `src/kno/mcp/servers/memory.py`, `src/kno/web/routes/facts.py`, `src/kno/web/templates/facts/list.html`.

### 0.15 Anti-loop / per-tool-call rate limit **[F]**
- Acceptance: inside a run, a tool may not be called more than 10× with semantically-equivalent args (SHA-256 of canonical-JSON args). 11th call raises `ToolLoopDetected`; agent receives this as a tool-result.
- Verify: synthetic test: a workflow that loop-calls `remember_fact("counter", n)` for n in range(20) is killed on the 11th call.
- Files: `src/kno/mcp/host.py` (extension), `tests/unit/test_anti_loop.py`.

### 0.16 LangGraph chat workflow runtime **[B]** *Depends on 0.8, 0.12, 0.13, 0.14, 0.15*
- Acceptance: `kno.workflows.kinds.chat.build_graph(workflow)` returns compiled graph with `retrieve → synth ↔ tools → end`. `read` tools auto-allow; non-`read` tools raise `NotImplementedError` (Phase 1 adds the simple approval gate).
- Verify: integration test: no-tool turn streams; tool turn invokes `remember_fact`; checkpointer persists.
- Files: `src/kno/workflows/kinds/chat.py`, `src/kno/agent/{graph.py, nodes/{retrieve.py, synth.py, tools.py}}`.

### 0.17 Reliability checks (boot-time + `/api/health`) **[F]** *Depends on 0.2, 0.6*
- Acceptance: boot-time probes: Anthropic credentials valid, Ollama embed model loaded, Ollama chat fallback model present, DB `integrity_check` passes. Each probe logs structured. `/api/health` returns `{ok, version, db: integrity_check_result, anthropic: ok_or_failed, ollama: ok_or_failed}`. Failing probes fail loud; server starts anyway with degraded banner.
- Verify: kill `KNO_ANTHROPIC_API_KEY` → boot logs warning; `/api/health` shows `anthropic: failed`. Wrong Ollama URL → `ollama: failed`.
- Files: `src/kno/services/health.py`, `src/kno/api/routes/health.py`.

### 0.18 Default workflow + persona + 2 skills **[F]** *Depends on 0.11, 0.12, P0-pre.4*
- Acceptance: `data.seed/workflows/default/workflow.yaml` with `kind: chat`, persona referencing `cite-sources` + `cost-aware-reasoning` skills; tools allow `mcp:remember_fact`, `mcp:load_file`, `mcp:peek_file`, `mcp:extract_file`.
- Verify: `POST /api/data/reload`; `GET /api/workflows` lists `default`.
- Files: `data.seed/workflows/default/{workflow.yaml, persona.md}`, plus copy-to-`data/` on first boot.

### 0.19 Chat API + SSE **[B]** *Depends on 0.16, 0.18*
- Acceptance: `POST /api/chat` returns SSE: `delta`, `tool_call`, `tool_result`, `run_complete`, `error`. Request body: `{workflow: str, message: str, thread_id?: str}`. New thread if `thread_id` is null; resume otherwise.
- Verify: `curl --no-buffer -X POST ...` streams events; final `run_complete` carries `{run_id, thread_id, total_cost_usd}`.
- Files: `src/kno/services/chat.py`, `src/kno/api/routes/chat.py`.

### 0.20 Chat UI with thread sidebar (resume support) **[B][P with 0.21]** *Depends on 0.19*
- Acceptance: `/ui/chat` shows workflow picker, message input, conversation pane (htmx-sse), and a **thread sidebar** listing the user's recent threads (per ADR-0018 item 1); clicking a thread resumes it with full message history rendered.
- Verify: manual: chat, get response, navigate away, return, click thread → full history visible; type → continues with cached system prompt.
- Files: `src/kno/web/{routes/chat.py, templates/chat/{index.html, sidebar_partial.html, message_partial.html}, static/htmx-sse.js}`.

### 0.21 Feedback rating UI + API **[P with 0.20]** *Depends on 0.19*
- Acceptance: 👍/👎 buttons under every message and at run level; optional comment textarea; `POST /api/runs/<id>/feedback` and `POST /api/runs/<id>/messages/<mid>/feedback`; writes `run_feedback` row.
- Verify: rate a message; row visible in DB and surfaced in `/ui/runs/<id>` timeline.
- Files: `src/kno/api/routes/feedback.py`, `src/kno/web/templates/chat/feedback_buttons.html`, `src/kno/services/feedback.py`. Migration 0001 already covered `run_feedback`.

### 0.22 Runs view (basic timeline) **[P with 0.20, 0.21]** *Depends on 0.19*
- Acceptance: `/ui/runs` lists user's runs; `/ui/runs/<id>` timeline shows model calls, tool calls (with args + result snippet), retrieved memory references, costs, latencies. Read-only.
- Verify: after a chat turn, the run appears with full timeline.
- Files: `src/kno/web/{routes/runs.py, templates/runs/{list.html, detail.html}}`, `src/kno/services/runs.py`, `src/kno/api/routes/runs.py`.

### 0.23 `kno` CLI (P0 subset) **[F]**
- Acceptance: unified `kno` Typer app with subcommands: `serve` (uvicorn), `backup` (VACUUM INTO + tar `data/`), `backup --config-only`, `restore <archive>`, `wipe --category <conversations|kb|semantic-facts|all> --confirm`, `version`. `pyproject.toml` exposes `kno = "kno.cli.main:app"`.
- Verify: `uv run kno serve` boots; `uv run kno backup` produces tarball; `restore` round-trips a wiped DB; `wipe --category conversations --confirm` clears runs/messages but preserves `semantic_facts`.
- Files: `src/kno/cli/{main.py, serve.py, backup.py, wipe.py, version.py}`.

### 0.24 Anthropic prompt caching (cache_control) **[F]** *Depends on 0.6*
- Acceptance: `kno.models.caching` uses anthropic SDK directly for calls needing `cache_control: ephemeral` on the system block. System-prompt ordering per ADR-0004.
- Verify: integration test: same system prompt twice within 5 min → second call's `model_calls.cached_tokens > 0`.
- Files: `src/kno/models/caching.py`, `docs/adr/0004-prompt-cache-ordering.md`.

### 0.25 ADR drafts: 0004, 0005, 0006 **[F]**
- Files: `docs/adr/{0004-prompt-cache-ordering, 0005-per-run-token-cache, 0006-semantic-fact-bootstrap}.md`.

### Phase 0 verification checkpoint
- [ ] `uv run kno serve` boots; all four reliability probes pass; `/api/health` returns 200.
- [ ] Google login works.
- [ ] **Daily-driver smoke test**: "Hey Kno, my name is Dylan. Remember that." Restart server. "Who am I?" → "You're Dylan." Cost <$0.05 across both turns.
- [ ] `/ui/facts` lists `name=Dylan`.
- [ ] `/ui/runs/<id>` shows full timeline including `remember_fact` tool call.
- [ ] 👍/👎 writes feedback row.
- [ ] `kno backup` + `kno restore` round-trip works.
- [ ] `kno wipe --category conversations --confirm` clears conversations only.
- [ ] Anti-loop test passes.
- [ ] `make test`, `make lint`, `make mypy` all green.
- [ ] `docs/verification/phase-0.md` committed with notes.

---

## Phase 1 — KB + Flow Coach (target: 2–3 weeks)

### 1.1 Migration 0002: KB tables **[B]** *Depends on 0.3*
- Acceptance: `kb_repos`, `kb_docs`, `kb_chunks(...,  embedding BLOB, fts_text TEXT)`; sqlite-vec extension loaded at boot; FTS5 virtual table `kb_chunks_fts(fts_text, content='kb_chunks', content_rowid='id')`.
- Verify: insert a chunk; vector search returns it; FTS search returns it.
- Files: `migrations/versions/0002_kb.py`, `src/kno/db/sqlite_vec_setup.py`.

### 1.2 Ollama embed client **[P with 1.3]**
- Acceptance: `embed_batch(texts) -> list[list[float]]` batched against Ollama; tested with `nomic-embed-text` (768-dim); 10s timeout per batch.
- Verify: integration test: embed 5 strings → 5 vectors of dim 768.
- Files: `src/kno/knowledge/embed.py`.

### 1.3 `RetrievalBackend` Protocol + `SqliteVecBackend` **[B]** *Depends on 1.1, 1.2*
- Acceptance: `RetrievalBackend` Protocol (per ADR-0015); `SqliteVecBackend` implements `upsert_chunk`, `delete_chunks_for_doc`, `hybrid_search`, `health`. Hybrid = BM25 (FTS5) + cosine (sqlite-vec) merged via RRF k=60. **`PgvectorBackend` deferred to v2** per ADR-0018; interface exists, no implementation.
- Verify: unit test: 20 synthetic chunks; hybrid search returns top-8 ranked sensibly.
- Files: `src/kno/knowledge/backends/{base.py, sqlite_vec.py}`, `tests/integration/test_retrieve.py`.

### 1.4 Hugo source repo ingestion **[B][S]** *Depends on 1.1, 1.2, 1.3, 1.10*
- Acceptance: `kno.knowledge.sources.hugo_repo` shallow-clones a repo; walks `content/`; parses frontmatter via `python-frontmatter`; heading-aware chunking via `markdown-it-py` (target 700 tok, 150 overlap). Citation = `<org>/<repo>@<sha>:<path>#L<a>-<b>`. Delta detection via `kb_repos.last_sha`.
- Verify: ingest `dvhthomas/bitsby-me` (or fixture); ≥50 chunks; re-run is a no-op; adding a post triggers only its delta.
- Files: `src/kno/knowledge/sources/{base.py, hugo_repo.py}`, `tests/integration/test_hugo_ingest.py`.

### 1.5 `kb_search` MCP server **[P with 1.6]** *Depends on 1.3, 0.7*
- Acceptance: `kb_search(query, k=8)` returns `[{chunk_id, content, citation_ref, score}]`. `action_category: read`. Scoped to current user.
- Verify: integration test: agent calls `kb_search`; chunks include citation strings.
- Files: `src/kno/mcp/servers/kb_search.py`.

### 1.6 Citation integrity check **[P with 1.5]** *Depends on 1.3*
- Acceptance: agent output post-processed: every citation ref like `org/repo@sha:path#Lx-y` is validated against `kb_chunks`; mismatches flagged with red badge in `/ui/chat`; agent **never sees** the validation result (no gaming).
- Verify: synthetic test: inject a hallucinated citation into a mocked response; UI renders the red badge; `kb_chunks` query log shows the validation attempt.
- Files: `src/kno/services/citations.py`, `src/kno/web/templates/chat/citation_partial.html`.

### 1.7 GitHub OAuth provider **[F]** *Depends on 0.4*
- Acceptance: `/api/auth/connect/github` initiates GitHub OAuth (`repo` scope); callback stores encrypted token in `service_connections`; `/ui/connections` lists the connection.
- Verify: connect; row appears; token decryptable.
- Files: `src/kno/auth/providers/github.py`, `src/kno/api/routes/connections.py`, `src/kno/web/routes/connections.py`.

### 1.8 `github` MCP server **[P with 1.9]** *Depends on 0.7, 1.7*
- Acceptance: tools `github_search_issues`, `github_read_file`, `github_repo_summary` (all `read`); uses connection token via per-run cache.
- Verify: integration test with a real token: `github_repo_summary("dvhthomas/kno")` returns title + description.
- Files: `src/kno/mcp/servers/github.py`.

### 1.9 `flowmetrics` MCP server **[P with 1.8]** *Depends on 0.7, 1.7 (GitHub OAuth)*
- Acceptance: tools `flowmetrics_cycle_time`, `flowmetrics_throughput`, `flowmetrics_aging_wip`, `flowmetrics_when_done`, `flowmetrics_how_many`, `flowmetrics_efficiency`, `flowmetrics_cfd`. All `read`. Subprocess wraps `uv run flow ... --format json`. Pydantic-validates the schema-versioned envelope against a captured fixture.
- **Auth pattern (per ADR-0019)**: no new credential row. flowmetrics inherits GitHub auth via the standard `GH_TOKEN` env var, sourced from the user's existing GitHub OAuth row in `service_connections` and decrypted via the per-run token cache (ADR-0005). Subprocess invocation: `env={"GH_TOKEN": decrypted, ...minimal_allowlist}`.
- Verify: integration test against `dvhthomas/kno`; full agent flow: ask flow-coach "how is the kno repo doing this month?" — response cites flowmetrics tool call(s), mentions P85 cycle time + aging WIP + one recommendation. Integration test also asserts `GH_TOKEN` is set in the subprocess env and the cached token is reused across calls in the same run (per ADR-0005 + ADR-0019).
- Files: `src/kno/mcp/servers/flowmetrics.py`, `tests/integration/test_flowmetrics_mcp.py`, `tests/fixtures/flowmetrics_envelope.json`.
- Pinning: pin `dvhthomas/flowmetrics` to a **specific commit SHA**, not a version (pre-alpha as of 2026-05-12; no releases yet). Re-snapshot the fixture envelope on every bump.
- **Deferred from v1**: `gh_velocity` MCP server. See `docs/notes/gh-velocity.md` for the trade-off and the triggers that would reintroduce it.

### 1.10 Simplified approval gate **[B]** *Depends on 0.7, 0.16*
- Acceptance: per ADR-0018: `read` tools auto-allow; any non-`read` tool triggers `interrupt_before` in LangGraph; UI banner with Approve/Deny only (no typed confirmation, no cooldown). Full 5-category model deferred to v2.
- Verify: synthetic `write`-category tool: turn pauses; click Approve resumes; Deny returns "denied by user" tool result.
- Files: `src/kno/mcp/host.py` (extension), `src/kno/agent/nodes/tools.py`, `src/kno/web/templates/chat/approval_banner.html`.

### 1.11 Seed: librarian + vacanti workflows + remaining skills **[F]** *Depends on 0.11, 0.12, 1.5, 1.8, 1.9*
- Acceptance: workflows `kb-qa` (persona = librarian; tools: `mcp:kb_search`, `mcp:remember_fact`) and `flow-coach` (persona = vacanti; tools: `mcp:flowmetrics`, `mcp:github`, `mcp:kb_search`, `mcp:remember_fact`). Skills already drafted in pre-flight `data.seed/skills/`.
- Verify: `POST /api/data/reload`; both workflows visible in `/ui/chat` picker.
- Files: `data.seed/workflows/{kb-qa,flow-coach}/{workflow.yaml, persona.md}`.

### 1.12 `kno ingest` CLI subcommand **[F]** *Depends on 1.4, 0.23*
- Acceptance: `kno ingest hugo-repo <org>/<repo>` runs the Hugo ingestion against a configured GitHub connection.
- Verify: `uv run kno ingest hugo-repo dvhthomas/bitsby-me` produces chunks; visible in `/ui/kb`.
- Files: `src/kno/cli/ingest.py`.

### 1.13 KB UI **[F]** *Depends on 1.4, 1.12*
- Acceptance: `/ui/kb` lists ingested repos per user; "Sync now" / "Forget" buttons; status indicators (chunk count, last_sha, last_ingested_at).
- Verify: manual: add a Hugo repo, observe sync progress, forget removes chunks.
- Files: `src/kno/web/{routes/kb.py, templates/kb/list.html}`.

### 1.14 Eval suite + `kno eval` CLI **[B]** *Depends on 0.6, 0.16*
- Acceptance: `data/evals/<workflow>/cases.yaml` schema (rubric: `must_include`, `must_call_tool`, `must_not_say`, `judge`, `max_cost_usd`). `kno eval <workflow>` runs every case against the active version; LLM-as-judge via Haiku; persists `eval_runs` + `eval_case_results` (need migration 0003 — see 1.15); prints pass/fail/cost table. **No bump-level lint, no auto-eval-on-save** per ADR-0018.
- Verify: write 5 cases for `flow-coach`; `kno eval flow-coach` runs them; results in DB; full suite cost < $0.30.
- Files: `src/kno/services/evals.py`, `src/kno/cli/evals.py`, `data.seed/evals/{default, kb-qa, flow-coach}/cases.yaml`.

### 1.15 Migration 0003: eval tables **[B][F]**
- Acceptance: `eval_runs`, `eval_case_results`.
- Files: `migrations/versions/0003_evals.py`.

### 1.16 Prompt injection test battery **[F]** *Depends on 1.4, 1.5*
- Acceptance: `tests/security/test_prompt_injection.py` fixtures with known attack patterns (instruction override, exfil-via-tool, encoded payloads); LLM-as-judge scores resistance per attack; threshold ≥8/10 average.
- Verify: `pytest tests/security/ -v` runs; aggregate score ≥ 8/10; failures point at specific attack-pattern files.
- Files: `tests/security/test_prompt_injection.py`, `tests/security/fixtures/attacks/*.md`.

### Phase 1 verification checkpoint
- [ ] `kno ingest hugo-repo dvhthomas/bitsby-me` → ≥50 chunks; visible in `/ui/kb`.
- [ ] `kb-qa` returns cited answer to a real query; citations validate (green badges); GitHub source links resolve.
- [ ] `flow-coach` returns a Vacanti-style summary for `dvhthomas/kno`; mentions p85 cycle time + one recommendation; mentions aged WIP if any; sourced from `flowmetrics` tool calls. Cost <$0.05.
- [ ] `kno eval kb-qa` passes all cases; total cost <$0.30.
- [ ] `kno eval flow-coach` passes all cases.
- [ ] Prompt-injection battery green (avg ≥8/10).
- [ ] Approval gate works: synthetic `write` tool pauses, approve resumes, deny returns denial.
- [ ] `docs/verification/phase-1.md` committed.

---

## Phase 2 — Refinement + Deploy (target: 1.5–2 weeks)

### 2.1 Migration 0004: refine_proposals **[B][F]**
- Files: `migrations/versions/0004_refine.py`.

### 2.2 `/admin/refine` page **[B]** *Depends on 2.1, 1.14*
- Acceptance: pick workflow + date range + filter (`all` / `👎 only`); Kno sends matched runs to Claude with a "propose a unified prompt diff plus rationale" prompt; UI shows diff with rationale; inline-editable; "Save as v<n>" runs eval before commit. **No rate limit** per ADR-0018. Proposals persisted in `refine_proposals` whether accepted or rejected.
- Verify: 👎 a flow-coach response; pick `flow-coach` + `👎 only` + last 14 days; Claude proposes diff; approve; new version active; eval runs.
- Files: `src/kno/services/refine.py`, `src/kno/web/{routes/admin.py, templates/admin/refine.html}`.

### 2.3 Workflow version diff + rollback **[F]** *Depends on 2.2*
- Acceptance: `/ui/workflows/<slug>/versions` shows version history; pairwise diff (server-side `difflib.HtmlDiff`); 1-click rollback to a previous version.
- Verify: edit + save a workflow; diff vs prior version visible; rollback restores; new chat uses the rolled-back version.
- Files: `src/kno/web/templates/workflows/{versions.html, diff.html}`.

### 2.4 Anthropic-outage fallback drill **[B]** *Depends on 0.6, 0.17*
- Acceptance: with `KNO_ANTHROPIC_API_KEY` unset (test env), a `default` chat turn produces a coherent response from Ollama `llama3.1` fallback. Coherence assessed by manual review of N=5 responses across different prompts. **If unusable, fail the phase honestly and document.**
- Verify: manual drill checklist in `docs/verification/phase-2.md` with the 5 prompts and assessments.
- Files: `docs/verification/phase-2.md` (verification artifact), code already in place via 0.6.

### 2.5 `kno rotate-keys` command + ops playbook **[F]** *Depends on 0.9*
- Acceptance: `kno rotate-keys` admin command re-wraps every `service_connections.*_enc` row under a new KEK. Documented playbook in `docs/ops.md` covering: backup first, run rotate-keys, verify subsequent tool calls work, retire old key.
- Verify: against test env: rotate; subsequent `gh_velocity` tool call works (token decrypt under new KEK).
- Files: `src/kno/cli/rotate_keys.py`, `docs/ops.md`.

### 2.6 Daily integrity-check cron **[F]** *Depends on 0.17*
- Acceptance: scheduled task runs `PRAGMA integrity_check`; opens most-recent backup tarball and queries a known row; structured-log alert on any failure.
- Verify: artificially corrupt a backup → next cron run logs a failure with the tar path; corrupt the DB → integrity_check logs failure.
- Files: `src/kno/services/integrity_cron.py`, `scripts/daily_integrity.py`.

### 2.7 Dockerfile + fly.toml **[B]** *Depends on every functional task*
- Acceptance: multi-stage Dockerfile (uv build → slim final w/ sqlite-vec extension included); `fly.toml` with one machine + persistent volume at `/data`; Fly secrets configured for all env vars.
- Verify: `fly deploy` from a fresh checkout; deployed `/api/health` returns 200.
- Files: `Dockerfile`, `fly.toml`, `.dockerignore`.

### 2.8 CI + deploy workflows **[F]** *Depends on 2.7*
- Acceptance: `.github/workflows/ci.yml` runs lint + mypy + test + eval suite. `.github/workflows/deploy.yml` runs on `main` push after CI passes: `fly deploy`.
- Verify: merge a small change; both workflows pass; deploy succeeds.
- Files: `.github/workflows/{ci.yml, deploy.yml}`.

### 2.9 README + ops doc finalization **[F]**
- Acceptance: README has quickstart (clone + uv sync + .env + `kno serve`); deploy-your-own walkthrough; troubleshooting. `docs/ops.md` finalized with: backup/restore, wipe, key rotation, adding an MCP server, adding a workflow, daily-driver expectations.
- Verify: a fresh contributor (or future-me) can follow it without asking questions.
- Files: `README.md`, `docs/ops.md`.

### 2.10 ADR-0012 draft (version retention) **[F]**
- Files: `docs/adr/0012-version-retention.md`.

### 2.11 One-week real-usage validation **[B][S]** *Depends on 2.7, 2.12, 2.13*
- Acceptance: Dylan uses Kno daily for 7 days. Daily review of `model_calls` ledger; weekly retrospective of `/admin/refine` outcomes (accepted vs rejected; eval-score deltas). **Includes one fresh-machine `kno setup` dry-run (2.12) and one `kno export` round-trip (2.13)** so both new commands get exercised on real data before v1 is called done.
- Verify: `docs/verification/v1-week-1.md` with cost summary + top surprises + refinement outcomes; total Anthropic spend < $10 for the week.
- Files: `docs/verification/v1-week-1.md`.

### 2.12 `kno setup` interactive wizard **[F]** *Depends on 0.23, 2.5*
- Acceptance per ADR-0018 §2.3 item 11: `uv run kno setup` walks the user through every `.env` value step-by-step.
  - Opens browser tabs to provider consoles via `webbrowser.open()` at the right moments (Anthropic keys page, Google Cloud Console credentials, GitHub Developer Settings OAuth Apps).
  - Prompts for paste-backs of client IDs, secrets, API keys (uses `getpass.getpass()` for secret-grade values).
  - Verifies each value works before continuing: Anthropic key against `messages` endpoint with a 1-token probe; Ollama against `/api/embeddings`; GitHub OAuth client by attempting the authorization URL.
  - Generates Fernet KEK and session secret automatically; never prompts for them.
  - Writes `.env` directly (mode 0600; gitignored).
  - **Resumable**: writes `.env.partial` after each step; re-running `kno setup` picks up where it left off; fully populated `.env` triggers "configuration complete; run `kno setup --reconfigure` to start over."
- Verify: from a fresh clone with no `.env`, `kno setup` walks to a working setup in ~15 minutes; second invocation against a complete `.env` says "complete; use --reconfigure"; ^C during the wizard preserves `.env.partial`; resume picks up cleanly.
- Files: `src/kno/cli/setup.py`, `src/kno/services/setup_validators.py`, `tests/integration/test_setup_wizard.py`.

### 2.13 `kno export` data portability **[F]** *Depends on 0.23*
- Acceptance per ADR-0018 §2.3 item 12: `uv run kno export [--category C] [--output PATH] [--format directory|tarball]`. Default produces `./kno-export-<UTC-timestamp>.tar.gz` containing:
  - `README.md` — machine-generated archive overview (what's inside, schema versions, timestamps, total bytes).
  - `conversations/<YYYY-MM-DD>-<thread-slug>.md` — one markdown per thread; timestamps, role headers, content, inline tool-call blocks; reverse-chronological.
  - `semantic_facts.json` — current facts as JSON (or `semantic_facts.md` for human reading).
  - `kb_sources/<provider>-<org>-<repo>/` — per-source dir; `_meta.json` with repo+sha pointers; reconstructed chunk text as `chunks/<doc>.md` with citation refs.
  - `model_calls.csv` — full cost ledger; one row per LLM call; columns `(ts, model, tokens_in, tokens_out, cached_tokens, cost_usd, run_id, workflow)`.
  - `feedback.json` — 👍/👎 ratings with run-id linkage and comments.
  - `connections.json` — list of `{provider, connection_label, scopes, created_at, last_used_at}`; **never includes the encrypted token values themselves**.
  - `workflows/`, `agents/`, `skills/` — straight copies from `data/` (already filesystem-as-truth).
  - `evals/` — eval cases + recent eval-run results.
  - `runs/<run_id>.json` — optional verbose timeline (off by default; `--verbose` includes them).
  - Per-category like `kno wipe`: `--category conversations|kb|semantic-facts|connections|all`.
- Verify: export from a populated test instance produces a readable archive; `cat conversations/*.md` shows human-readable threads; `connections.json` contains zero `*_enc` fields; round-trip with `kno backup` is unaffected (export is read-only, doesn't touch DB state); same-day export is idempotent.
- Files: `src/kno/cli/export.py`, `src/kno/services/export.py`, `tests/integration/test_export.py`.

### Phase 2 verification checkpoint = v1 release
- [ ] End-to-end refinement cycle works on a real 👎 case.
- [ ] Eval re-run on new version: pass count ≥ prior version.
- [ ] `kno rotate-keys` successfully rotates encryption.
- [ ] Anthropic-outage drill: Ollama fallback produces coherent responses. (If not, drill failed → document and decide whether to ship with no fallback or fix.)
- [ ] `kno wipe --category all --confirm` on a test deploy zeros user data cleanly.
- [ ] **`kno setup` works on a fresh machine** — clone a fresh copy, run the wizard, end up with a working `.env` and Kno running. (Per ADR-0018 §2.3 item 11.)
- [ ] **`kno export` produces a human-readable archive** — extract it, open `conversations/*.md` in a text editor, the threads are legible; `connections.json` contains zero token values. (Per ADR-0018 §2.3 item 12.)
- [ ] Deployed at `kno.fly.dev`; `/api/health` returns 200; login works.
- [ ] One full week of real usage; spend < $10.
- [ ] All ADRs through 0019 in `docs/adr/` are drafted.
- [ ] `docs/verification/phase-2.md` and `v1-release.md` committed.

---

## Deferred to v2 (per ADR-0018 and subsequent decisions)

Captured here so they're visible and not forgotten:

- **`gh_velocity` MCP server** — deferred per `docs/notes/gh-velocity.md` (post-pre-flight review). flowmetrics covers v1 needs; gh-velocity returns to the table if specific triggers fire (see notes file).

- Multi-user: allowlist enforcement, isolation CI battery, invite flow, per-user budget caps, comprehensive `UserScopedSession` tests
- Panel of Experts (entire workflow kind, panelist agents, integrator, structured-output node, partial-failure handling, per-panelist drill-down) — ADRs 0007, 0008, 0009
- Subagent runtime spawn mechanism
- Approval gate elaborations (typed confirmation, cooldowns, `external_messaging`, `irreversible`, `/admin/approvals`, per-user policy overrides) — ADR-0016
- KB sources beyond Hugo: generic GitHub markdown, Google Drive folders, direct uploads (PDF/MD/TXT), HTTP crawler
- Multi-provider OAuth scaffolding (Slack, Notion, Granola)
- Refinement rate limit, bump-level lint, auto-eval-on-save — ADRs 0013, 0014
- Cost kill switch, per-day/month caps
- Git-backed `data/` — ADR-0017
- `PgvectorBackend` implementation (interface ships in v1 per ADR-0015)
- Agent primitive layer (collapsed to Workflow in v1)
- DSPy offline tool
- Slack adapter (chat surface)
- Scheduled / webhook workflow triggers
- Dashboards (Larson loop 4)
- Cross-workflow eval batteries
- Refinement dashboards
- Shell-tool sandbox — ADR-0003 (no shell tool in v1)
- `co-planner` workflow + calcmark MCP (depends on OQ-1)
- `coordinator: script` deterministic escape hatch

---

## ADR ledger (Kno-Lite)

| # | Title | v1? | File |
|---|---|---|---|
| 0001 | LiteLLM gateway | ✅ | `docs/adr/0001-litellm-gateway.md` |
| 0002 | LangGraph state machine | ✅ | `docs/adr/0002-langgraph-state-machine.md` |
| 0003 | Shell sandbox | v2 | `docs/adr/0003-shell-sandbox.md` |
| 0004 | Prompt-cache block ordering | ✅ (draft P1) | `docs/adr/0004-prompt-cache-ordering.md` |
| 0005 | Per-run token cache | ✅ (draft P0) | `docs/adr/0005-per-run-token-cache.md` |
| 0006 | Semantic-fact bootstrap UX | ✅ (draft P0) | `docs/adr/0006-semantic-fact-bootstrap.md` |
| 0007 | Panel artifact fetch | v2 | (deferred) |
| 0008 | Partial-panel failure | v2 | (deferred) |
| 0009 | Tool-allowlist intersection | v2 | (deferred) |
| 0010 | Multi-user isolation | ✅ downgraded | `docs/adr/0010-multi-user-isolation.md` |
| 0011 | Checkpointer colocation | ✅ | `docs/adr/0011-checkpointer-colocation.md` |
| 0012 | Version retention | ✅ (draft P2) | `docs/adr/0012-version-retention.md` |
| 0013 | Bump-level lint | v2 | (deferred) |
| 0014 | Refinement rate limit | v2 | (deferred) |
| 0015 | KB substrate portability | ✅ (subset) | `docs/adr/0015-kb-substrate-portability.md` |
| 0016 | Interrupt resume | v2 | (deferred) |
| 0017 | Git-backed data | v2 | (deferred) |
| **0018** | **Kno-Lite scope decision** | ✅ | `docs/adr/0018-kno-lite-scope.md` |

---

## Definition of done (Kno-Lite v1)

Every `[ ]` above is `[x]`; every Phase verification checkpoint has a `docs/verification/phase-<N>.md` record; the 9 v1 ADRs are all drafted; `docs/spec.md` is reviewed and any drift is corrected.

Then: **one week of real daily-driver use under $10 Anthropic spend** is the lived definition of done. Specs and verifications matter; daily use is the truth.
