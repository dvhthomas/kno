# Kno-Lite — Implementation Plan

> **Source spec:** `docs/spec.md` v0.9 (full design vision; v1 scope per **ADR-0018**)
> **Scope:** Kno-Lite (per ADR-0018) — single user, daily-driver "pi.ai play"
> **Status:** Phase 2 (Plan), v2 (post-ADR-0018 rewrite)
> **Last updated:** 2026-05-12
> **Companion:** `docs/tasks.md` — operational task list

---

## 1. Executive summary

Kno-Lite v1 ships in **3 phases + pre-flight** over **~6 weeks** of single-developer focused work. The goal is the daily-driver personal AI the owner described — a system to depend on, refine, and learn from, that he built himself.

Headlines:

- **Vertical slicing** still applies. Each phase ends with a runnable demo that exercises a complete user journey.
- **Phase 0 ends with a working chat** that remembers you across sessions. That alone is the v0 product.
- **Phase 1 adds the KB and the Flow Coach** — Kno becomes useful for "answer about my writing" and "how's my repo doing."
- **Phase 2 adds the refinement loop and ships to Fly** — Kno becomes a system that improves with use, available wherever you are.
- **17 ADRs from the full spec are scoped per ADR-0018**: 9 apply to v1, 8 defer to v2.

---

## 2. Strategy: still vertical, still slicing, smaller surface

The previous plan's slicing rule still holds: each phase ends with a runnable end-to-end slice — UI → API → agent → tool → DB. The difference is that we're slicing through **less stack**:

- No multi-tenant DB layer to honor at every query (one user; `UserScopedSession` still ships but is exercised by smoke tests, not the elaborate isolation suite).
- No Panel runtime to design around.
- No approval-gate elaboration (just `read` auto / `write` paused).
- No multi-provider OAuth scaffolding (Google + GitHub only).
- One KB source kind (Hugo repos).

The smaller surface makes each phase actually fit in its calendar.

---

## 3. Phase summary

| Phase | Demo gate | Calendar |
|---|---|---|
| **Pre-flight** | OQ-2 resolved; dev env up; Anthropic / Google / GitHub credentials provisioned; Ollama running with `nomic-embed-text`; initial skill seeds chosen | 2–3 days |
| **0** Foundation + Chat | "Hey Kno, my name is Dylan. Remember that." → response. Restart server. Tomorrow: "Who am I?" → "You're Dylan." Cost <$0.05 across both turns. | 2 weeks |
| **1** KB + Flow Coach | Ask Kno about a Bitsby post by topic → cited answer, citations validate. "How is dvhthomas/kno doing this month?" → Vacanti-style answer. Eval suite runs and passes for both workflows. | 2–3 weeks |
| **2** Refinement + Deploy | 👎 a flow-coach response in `/ui/chat` → `/admin/refine` proposes a prompt diff → approve → next response is measurably better → eval suite still green. Deployed at `kno.fly.dev`. | 1.5–2 weeks |

**Total: ~6 weeks** with one focused developer.

---

## 4. Dependency graph

```
Pre-flight  ─►  Phase 0  ──►  Phase 1  ──►  Phase 2
                Foundation     KB +          Refinement +
                + Chat         Flow Coach    Deploy
                  │              │             │
                  └──────────────┴─────────────┘
                       Shared: feedback rating,
                       inspection, reliability checks,
                       semantic memory
```

**No cross-phase blocking** between 1 and 2 — they could theoretically run in parallel, but a solo developer should serialize.

---

## 5. Phase-by-phase plan

### Pre-flight (2–3 days)

Resolve the blocking knowns before any code:

1. **OQ-2** — spike on `gh-velocity` output shape. 30 min reading its README + 30 min trying it on `dvhthomas/kno`. Outcome: a `docs/notes/gh-velocity.md` with the actual JSON/text format we'll consume.
2. **Dev environment**:
   - Python 3.12 via `uv python install 3.12`
   - `uv` itself current
   - Ollama installed with `nomic-embed-text` (~700MB) and a fallback chat model (`llama3.1:8b` ~5GB or `llama3.1:70b` if hardware allows)
   - `.env.example` populated and a working `.env`
3. **Credentials**:
   - Anthropic API key (organization billing on Max plan — $30/mo target informs ledger thresholds)
   - Google OAuth client + secret (Web application, `http://localhost:8000/api/auth/google/callback` as authorized redirect)
   - GitHub OAuth app (same redirect pattern) — minimal scope `repo` for now
4. **Initial skill seeds chosen**: small list of skills to ship in Phase 0. Proposed:
   - `cite-sources`
   - `vacanti-metrics`
   - `flow-jargon`
   - `monte-carlo-explainer`
   - `cost-aware-reasoning` (per ADR-0018 §2.3 item 10)

Each skill is a 1–2 page markdown body the owner writes (or has Kno-the-design-process draft) before Phase 0 ends.

---

### Phase 0 — Foundation + Chat (2 weeks)

**Goal:** smallest possible runnable Python server that you can chat with. It remembers you. Restart-safe. Cost-aware. Reliable enough to use daily from day one.

#### Deliverables (in approximate dependency order)

1. **Project skeleton**: `pyproject.toml` with pinned deps, `uv.lock`, ruff + mypy --strict + pytest + pre-commit, Makefile.
2. **Config layer** (`kno.config`): pydantic-settings; required env vars; fail-fast on missing.
3. **Database (Migration 0001)**: `users`, `sessions`, `service_connections`, `model_calls`, `runs`, `messages`, `tool_calls`, `audit_log`, `semantic_facts`. SQLite WAL. SQLAlchemy 2.x async. `UserScopedSession` wrapper ships (per ADR-0010, downgraded — single-user verification only).
4. **LangGraph base** (per ADR-0002): `AgentState` TypedDict including `budget_remaining_usd` field (item 10 from ADR-0018 §2.3). `AsyncSqliteSaver` checkpointer pointed at `data/kno.db` (per ADR-0011).
5. **LiteLLM client + ledger** (per ADR-0001): routing aliases, success/failure callbacks → `model_calls`. Fallback to Ollama configured for `synth` alias.
6. **MCP host scaffolding** (per ADR-0007 lite): empty registry; `Connection` interface; per-run token cache (per ADR-0005).
7. **Token vault with envelope encryption** (per ADR-0018 §2.3 item 7): Fernet for column-level encryption; documented `kno rotate-keys` command (implementation may be Phase 2).
8. **Google OAuth (identity)**: `authlib`; signed session cookies; `users` row on first login; **no allowlist enforcement** beyond `KNO_ADMIN_EMAIL` matching.
9. **Skill loader + registry**: parse `data/skills/<slug>/SKILL.md` with frontmatter.
10. **Workflow loader + registry**: parse `data/workflows/<slug>/workflow.yaml` with inline persona. `kind: chat` only. **No Agent primitive layer** (collapsed into workflow.persona per ADR-0018).
11. **Working memory + virtual files** (per spec §11.1, Larson): in-context buffer with token accounting; 80%-window compaction node; `load_file`/`peek_file`/`extract_file` tools for content > 10k tokens.
12. **Semantic memory + `remember_fact` tool** (per ADR-0018 §2.3 item 2): `semantic_facts(user_id, key, value)` table; `<user_facts>` block prepended to system prompt; a `remember_fact(key, value)` MCP tool with `action_category: internal_write` for agent self-write; `/ui/facts` for owner direct edits.
13. **Anti-loop / per-tool-call rate limit** (per ADR-0018 §2.3 item 4): inside one run, no tool called more than 10× with semantically-equivalent args.
14. **`default` workflow + persona + 1–2 skills**: just chat. No KB tools yet. Uses semantic memory + working memory.
15. **Reliability checks** (per ADR-0018 §2.3 item 3): boot-time probes for Anthropic credentials, Ollama health (embed + chat), DB integrity; logged and surfaced at `/api/health`.
16. **Chat API + UI**: `POST /api/chat` (SSE: `delta`, `tool_call`, `tool_result`, `run_complete`, `error`); `/ui/chat` with HTMX SSE pane, thread sidebar showing recent threads, click-to-resume per ADR-0018 §2.3 item 1.
17. **Feedback rating (per ADR-0018 §2.3 — feedback loop is v1)**: 👍/👎 + comment per message and per run; `run_feedback` table.
18. **Runs view (basic)**: `/ui/runs` list + `/ui/runs/<id>` timeline with model calls, tool calls, retrieved memory, cost.
19. **`kno` CLI (Phase 0 subset)**: `kno serve`, `kno backup` (`VACUUM INTO` + tar `data/`), `kno restore`, `kno wipe --category` (per ADR-0018 §2.3 item 8 — data deletion contract).
20. **Anthropic prompt caching** (per spec §15 / ADR-0004 pending draft): `cache_control: ephemeral` on system prompt block via anthropic-direct path.

#### Verification (gates Phase 1)

- [ ] `uv run kno serve` boots cleanly; all four reliability probes pass; banner shows model versions + commit SHA.
- [ ] Open `/ui/login`, log in via Google, see `/ui/chat` with the default workflow selected.
- [ ] **Daily-driver smoke**: Type "Hey Kno, my name is Dylan. Remember that." Wait for response. **Close browser, kill server, restart.** Open `/ui/chat`. Click yesterday's thread. Type "Who am I?" Response: "You're Dylan." Cost <$0.05 across both turns.
- [ ] `/ui/facts` shows the `name=Dylan` semantic fact; can be edited or deleted by hand.
- [ ] `/ui/runs/<id>` shows the full timeline including the `remember_fact` tool call from turn 1.
- [ ] 👍/👎 on a message writes a `run_feedback` row.
- [ ] `kno backup` produces a tar.gz; `kno restore <archive>` against a wiped data dir restores both the SQLite DB and the file-based config.
- [ ] `kno wipe --category conversations` removes all `runs`, `messages`, `tool_calls`, `model_calls`, `run_feedback` rows for the current user; leaves `semantic_facts` untouched.
- [ ] Anti-loop test: a synthetic workflow that calls `remember_fact("counter", "<n>")` in a loop is killed after 10 invocations.
- [ ] `make test`, `make lint`, `make mypy` all green.

#### ADRs to draft in Phase 0

- ADR-0004 (prompt cache block ordering)
- ADR-0005 (per-run token cache)
- ADR-0006 (semantic-fact bootstrap UX)
- ADR-0001, 0002, 0010-lite, 0011, 0018 already drafted

---

### Phase 1 — KB + Flow Coach (2–3 weeks)

**Goal:** Kno becomes useful for the two highest-value flows: cited Q&A over your writing, and Vacanti-style analysis of your projects.

#### Deliverables

1. **Migration 0002**: `kb_repos`, `kb_docs`, `kb_chunks` (with `embedding BLOB` + `fts_text`). sqlite-vec extension loaded at boot; FTS5 virtual table created.
2. **Ollama embed client** (`kno.knowledge.embed`): batched `nomic-embed-text` embedding.
3. **`RetrievalBackend` Protocol** (per ADR-0015): the interface ships; only `SqliteVecBackend` is implemented in v1. `PgvectorBackend` deferred to v2.
4. **Hugo source repo ingestion** (`kno.knowledge.sources.hugo_repo`): shallow clone, walk `content/`, parse frontmatter, heading-aware chunking. Per-repo delta detection via `kb_repos.last_sha`. **Only KB source in v1.**
5. **Hybrid retrieval** (BM25 via FTS5 + cosine via sqlite-vec, merged with RRF k=60): top-8 by default.
6. **`kb_search` MCP server**: `kb_search(query, k=8)` returns chunks with citation refs (`repo@sha:path#L<a>-<b>`). `action_category: read`.
7. **Citation integrity check** (per ADR-0018 §2.3 item 5): citation refs in agent output validated against `kb_chunks` at render time; failures shown as red badges; agent doesn't see the validation result.
8. **GitHub OAuth + `github` MCP** (per Phase 1 task 1.8 from original plan): `github_search_issues`, `github_read_file`, `github_repo_summary`. All `read`.
9. **`gh_velocity` MCP server**: `gh_velocity_repo_metrics(repo, since)` returning Vacanti metrics. `read`. **Pre-req: OQ-2 resolved in Pre-flight.**
10. **Seed: `librarian` persona + `vacanti` persona + remaining skills** under `data/workflows/{kb-qa,flow-coach}/` and `data/skills/`.
11. **`kb-qa` workflow**: `kind: chat`, persona inline, tools allow `mcp:kb_search` + `mcp:remember_fact`.
12. **`flow-coach` workflow**: `kind: chat`, persona inline, tools allow `mcp:gh_velocity`, `mcp:github`, `mcp:kb_search`, `mcp:remember_fact`.
13. **Approval gate (simplified, per ADR-0018)**: `read` auto-allow; **`write`** (any non-read category) pauses via LangGraph `interrupt_before`; UI banner with Approve/Deny. No typed confirmation, no cooldown. The full 5-category model is documented for v2.
14. **Eval suite + `kno eval <workflow>` CLI** (per ADR-0018 — simple version): YAML cases, Haiku-judge, prints pass/fail/cost. **No auto-run on save**, **no bump-level lint**. Run manually after edits.
15. **Prompt injection test battery** (per ADR-0018 §2.3 item 6): `tests/security/test_prompt_injection.py` fixtures with known attack patterns; LLM-as-judge scores resistance; runs in Phase 1 verification.
16. **Eval seed cases**: 5 cases each for `default`, `kb-qa`, `flow-coach`. Cover happy path + 1 known failure mode per workflow.
17. **Workflow editing UI** (`/ui/workflows`): list, detail with tabs (Persona / Skills / Tools / Versions / Test). "Save new version" writes a new row + the version markdown file. No bump-level lint in v1; the lint is documented for v2.

#### Verification (gates Phase 2)

- [ ] `kno ingest hugo-repo dvhthomas/bitsby-me` ingests ≥ 50 chunks; visible in `/ui/kb`. Re-run is a no-op (delta detection works).
- [ ] `kb-qa` returns a cited answer to "What did I write about evidence-based scheduling?"; citation links to GitHub source view; citation integrity check is green.
- [ ] `flow-coach` returns a Vacanti-style summary for `dvhthomas/kno`; includes p85 cycle time + one recommendation. Cost < $0.05.
- [ ] `kno eval kb-qa` runs all cases, prints pass/fail with cost; total cost < $0.30 for the suite.
- [ ] `kno eval flow-coach` likewise.
- [ ] Prompt injection battery green: known attack patterns in KB content do not cause the agent to violate the system prompt; LLM-as-judge averages ≥ 8/10 on resistance.
- [ ] Approval gate test: a synthetic `write`-category tool triggers the UI banner; click Approve resumes the run; Deny returns control to agent with denial message.

#### ADRs to draft

- ADR-0004 (if not already in P0)
- ADR-0015 already drafted; verify the Pgvector deferral wording matches Kno-Lite scope

---

### Phase 2 — Refinement + Deploy (1.5–2 weeks)

**Goal:** Kno gets measurably better with use, and lives at a URL you can hit from anywhere.

#### Deliverables

1. **`/admin/refine` page**: pick workflow + date range + filter (`👎 only` / `all`); Kno sends matched runs to Claude with a "propose targeted prompt diff" prompt; UI shows diff + rationale; inline edit; "Save as v<n>" runs eval before commit. **No rate limit** (single user; per ADR-0018).
2. **`refine_proposals` table**: every proposal persisted whether accepted or rejected.
3. **Workflow version diff view** in `/ui/workflows/<slug>/versions`: pairwise diff + ability to roll back active version with one click.
4. **Anthropic-outage fallback usability test** (per ADR-0018 §2.3 item 9): kill Anthropic credentials in test env, fire a default-chat turn, verify Ollama (`llama3.1`) produces a coherent response. If not, **fail Phase 2** and reconsider the failover story.
5. **Migration 0003**: `refine_proposals` + any final schema additions.
6. **Token-vault rotation playbook + `kno rotate-keys`** (per ADR-0018 §2.3 item 7): documented in `docs/ops.md`; CLI command re-wraps every `service_connections.*_enc` value under a new KEK.
7. **Daily integrity-check cron** (per ADR-0018 §2.3 item 3): `PRAGMA integrity_check`; backup validity check (open the most recent backup, query a known row); alerts via structured log if either fails. On Fly, runs as a scheduled machine.
8. **Dockerfile + `fly.toml`**: multi-stage build with sqlite-vec extension; Fly volume for `data/`; secrets configured.
9. **GitHub Actions**:
   - `.github/workflows/ci.yml` — lint + type + test + eval suite
   - `.github/workflows/deploy.yml` — push to `main` → `fly deploy`
10. **README + ops doc**: clone + setup + run locally; Fly deploy; data deletion; key rotation; backup/restore; how to add a new workflow.
11. **One-week real-usage validation**: Dylan uses Kno daily for 7 days. Daily review of `/admin/cost` (a small admin page summing `model_calls`); weekly retrospective of `/admin/refine` outcomes (which proposals were accepted, which rejected, which improved eval scores).

#### Verification (v1 release gate)

- [ ] End-to-end refinement cycle: 👎 a flow-coach response with a written comment; open `/admin/refine`; pick `flow-coach` + `👎 only` for last 7 days; Claude proposes diff with rationale; approve; new version is active; next flow-coach turn for the same query produces a measurably different (and ideally better) response.
- [ ] Eval suite re-run on the new version: total pass count is ≥ prior version's pass count.
- [ ] `kno rotate-keys` against a test env: re-wraps every connection token; subsequent tool calls still succeed (token decrypt with new KEK works).
- [ ] **Anthropic-outage drill** (manual): set `KNO_ANTHROPIC_API_KEY=""`; fire `default` chat turn; Ollama fallback produces a coherent response; banner visible in `/ui/chat` warning of degraded service.
- [ ] `kno wipe --category all --confirm` on a test deploy zeros all user data; restart server; user is fresh.
- [ ] Deployed at `kno.fly.dev` (or whatever domain); `/api/health` returns 200; first login works.
- [ ] One full week of normal use: total Anthropic spend < $10. Pin Kno to dock as a PWA.

#### ADRs to draft

- ADR-0012 (version retention — full history; rows are tiny)

---

## 6. Parallelism map

Solo-developer expectation, so parallelism is mostly "what tasks within a phase can be done in any order." For each phase:

| Phase | Independently doable |
|---|---|
| 0 | DB + migrations alongside Google OAuth; LiteLLM client alongside MCP host scaffolding; chat UI alongside chat API once services layer exists |
| 1 | Hugo source ingest alongside `gh_velocity` MCP; eval suite scaffolding alongside KB indexing; citation integrity check alongside approval gate UI |
| 2 | Refinement page alongside Fly deploy; key rotation alongside integrity cron |

If pair-programming with Claude becomes useful here, send Claude into a worktree on one branch and review.

---

## 7. Verification checkpoints

Each phase's "Verification" section is a hard gate. Commit verification records at `docs/verification/phase-<N>.md` (one file per phase) noting date, what passed, any deferred items.

**Hard rule unchanged from prior plan**: no Phase-N+1 work begins until Phase-N verification is fully green.

---

## 8. Risk register (Kno-Lite-scoped)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LiteLLM `cache_control` doesn't fully cover Anthropic ephemeral blocks | Med | Med | Anthropic-direct escape hatch in `kno.models.caching` (per ADR-0001); tested early in P0 |
| Hugo repo ingestion misses frontmatter edge cases | Med | Low | Test against all three target repos (`dvhthomas/bitsby-me`, `calcmark/calcmark-org`, `alwaysmap/recipes4me-org`) in P1 |
| Ollama fallback model is *technically working* but practically useless | Med | High | Phase 2 verification includes the actual outage drill; if it fails, we fail honestly rather than ship vapor |
| Prompt-injection battery reveals real vulnerabilities late | Low | High | Ship the battery in P1 (not P2); fix or document; defer ingestion of obviously-hostile sources until v2 |
| OQ-2 (gh-velocity output shape) discovers a fundamental shape mismatch | Med | Med | Pre-flight spike before any P0 work; fallback = wrap the CLI as a subprocess instead of importing as a library |
| Sub-OQ: Hugo source repo ingestion is slower than expected (some repos are huge) | Low | Low | Cap initial ingest at the most-recent N posts per repo; expand later |

---

## 9. ADR ledger (Kno-Lite scoped)

| # | Title | v1? | Status |
|---|---|---|---|
| **0001** | LiteLLM as model gateway | ✅ v1 | drafted |
| **0002** | LangGraph as agent state machine | ✅ v1 | drafted |
| 0003 | Shell-tool sandbox | ⏸ v2 (no shell tool in v1) | drafted |
| 0004 | Prompt-cache block ordering | ✅ v1 | pending (P1) |
| 0005 | Per-run decrypted-token cache | ✅ v1 | pending (P0) |
| 0006 | Semantic-fact bootstrap UX | ✅ v1 | pending (P0) |
| 0007 | Panel artifact fetch + size-cap | ⏸ v2 (no panel) | open |
| 0008 | Partial-panel failure semantics | ⏸ v2 | open |
| 0009 | Tool-allowlist intersection | ⏸ v2 | open |
| **0010** | Multi-user isolation enforcement | ✅ v1 (downgraded) | drafted |
| **0011** | Checkpointer colocation | ✅ v1 | drafted |
| 0012 | Version retention | ✅ v1 | pending (P2) |
| 0013 | Bump-level lint rules | ⏸ v2 | open |
| 0014 | Refinement rate limit | ⏸ v2 | open |
| **0015** | KB substrate + portability (interface ships; only SqliteVecBackend implemented) | ✅ v1 (subset) | drafted |
| 0016 | Interrupt resume semantics | ⏸ v2 (v1 approval is "click approve") | open |
| 0017 | Git-backed data sync | ⏸ v2 | open |
| **0018** | Kno-Lite scope decision | ✅ v1 | drafted |

**Net for v1**: 9 ADRs apply; 8 deferred. 6 already drafted; 3 to draft during the build.

---

## 10. Open questions (Kno-Lite scoped)

| OQ | Question | Resolve before | Default if unresolved |
|---|---|---|---|
| **OQ-1** | calcmark.org API or scrape? | Out of scope for v1 (co-planner deferred) | — |
| **OQ-2** | gh-velocity machine-readable output? | **Pre-flight** | Block P0 start until 30-min spike resolved |
| OQ-3 | Hugo from repo vs HTML | — | RESOLVED |
| OQ-4 | Hard $ kill-switch number | Out of scope (no kill switch in Kno-Lite) | — |
| OQ-5 | Shell-sandbox threat model | Out of scope (no shell in Kno-Lite) | — |
| OQ-6 | Initial invitees | Out of scope (single user) | — |
| OQ-7 | Version retention | P2 | Full history |
| OQ-8 | OAuth scopes per provider | Google + GitHub only; pre-resolved | — |
| OQ-9 | Git-backed data — v1 or v1.5? | Out of scope for v1 | — |
| OQ-10 | Panel orchestration variant | Out of scope (no panel) | — |
| OQ-11 | Initial policy.yaml | Out of scope (no policy.yaml in Kno-Lite — too few tools to need it) | — |
| OQ-12 | CLI approval UX | RESOLVED (browser-only) | — |
| OQ-13 | DSPy revisit triggers | v2 | — |
| OQ-14 | Eval bump-level lint rules | Out of scope (no auto-eval-on-save in v1) | — |

**Net**: only OQ-2 is blocking. Everything else is either resolved or out of scope for v1.

---

## 11. After v1

When v1 is in daily use, the v2 prompt is **NOT** "build the rest of v0.8 spec." It's: "what does real daily use of Kno-Lite reveal about what to add next?"

Likely candidates (in rough priority order, to be re-prioritized post-v1):

1. **Real second user** (per ADR-0018 — triggers re-activating multi-user infrastructure).
2. **Episodic memory** ("we talked about X last week") if daily use surfaces the gap.
3. **More KB sources** (Drive folder for `jobs4me`-style structured data; direct PDF uploads).
4. **Panel of Experts** if the use case surfaces a real need (probably during "I want to assess my own program plan from multiple angles" moment).
5. **Slack adapter** if the question surface migrates off the browser.
6. **`co-planner` + calcmark MCP** if OQ-1 resolves.
7. **PR-style review on workflow edits** if a second user appears.

The v2 plan starts when v1 is real, not before.

---

## 12. Change log

| Date | Author | Change |
|---|---|---|
| 2026-05-12 | Kno (drafted), Dylan (owner) | v1 plan based on spec v0.6, 7 phases |
| 2026-05-12 | Kno | v2 plan — Kno-Lite scope (per ADR-0018), 3 phases + pre-flight, ~6 weeks |
