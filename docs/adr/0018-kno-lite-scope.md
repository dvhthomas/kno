# ADR-0018: Scope reduction to Kno-Lite for v1

**Status:** Accepted
**Date:** 2026-05-12
**Drafted in phase:** Pre-Phase-0 (scope reset before implementation begins)
**Spec refs:** All of §1–§24 (this ADR scopes the spec into v1 / v2 buckets)
**Related ADRs:** All previously-drafted ADRs remain valid; their applicability is scoped per this ADR.

---

## 1. Context

The spec went through 8 iterations (v0.1 → v0.8) and grew in scope at each turn. Key adds along the way:
- v0.3: multi-user (3–10 trusted invitees)
- v0.4: Panel of Experts (multi-agent composition)
- v0.5: agent as first-class primitive separate from workflow
- v0.6: multi-provider OAuth scaffolding (Slack, Notion, Granola)
- v0.7: substrate portability (`RetrievalBackend`, dual implementations)
- v0.8: unified `kno` entry point (a *removal*, the only one)

A planning audit ("adversarial hat") surfaced that **the use cases are remarkably solo**:
- "How is *my* repo doing"
- "Answers from *my* sites"
- "*My* planning tool"
- A panel reviewing artifacts — still on *my* artifacts

The owner has not been able to name the other users (OQ-6 remained open through 8 versions). The audit also flagged:
- Three-quarters of v1 capability could be obtained with Claude Projects + Claude Code + 50 lines of glue.
- "Corporate/team" framing was aspirational; never grounded in real humans.
- Multi-user infrastructure, approval gate elaborations, Panel of Experts, multi-provider OAuth scaffolding, refinement rate limiting, etc. — all solving problems that don't yet exist.

**The owner re-stated the actual aspiration** that prompted this ADR:

> "Aspirationally, I just want to learn how to build, deploy, refine a real agentic system that I will depend on rather than using Claude for everything. It's the pi.ai play for me."

This is **categorically different** from "build a corporate/team agentic system":
- **Personal AI you depend on**, not a multi-tenant product
- **Daily-driver dependability**, not feature ceiling
- **Memory + refinement**, not capability breadth
- **Replace "Claude for everything"**, not "compete with Anthropic"

The spec's accumulated infrastructure mostly serves the team/corporate framing. The personal/daily-driver framing has different load-bearing concerns:
- Reliability over breadth
- Personal memory ("Kno knows me") over data isolation
- Cost predictability over budget enforcement infrastructure
- Improvement loop over many workflows
- Conversational quality over multi-agent debate

## 2. Decision

**Ship Kno-Lite as v1.** The full spec (v0.8) remains the design vision and v2 roadmap, but is not what gets built first.

Kno-Lite is the **brutally simple** version of Kno, optimized for "a personal AI I depend on daily that I built myself and that improves with use."

### 2.1 What's in v1 (Kno-Lite)

| Concern | In v1 |
|---|---|
| **Users** | Single user (the owner). Google OAuth still wired (for parity with Fly deploy) but no allowlist enforcement; the configured `KNO_ADMIN_EMAIL` is the only valid user. |
| **Deployment** | Two modes: laptop (`uv run kno serve` on `localhost:8000`) and Fly.io (`fly deploy`). Same code, runtime choice. Self-hosted server doc dropped from §1 — too many implicit obligations. |
| **Runtime stack** | Python 3.12 + uv, FastAPI + HTMX, LangGraph + `langgraph-checkpoint-sqlite`, LiteLLM (Anthropic Sonnet + Haiku), Ollama embeddings, MCP. Per ADR-0001, ADR-0002. |
| **Substrate** | SQLite (WAL) + sqlite-vec + FTS5 in `data/kno.db`. **Only the `SqliteVecBackend`** is built. The `RetrievalBackend` Protocol interface is preserved per ADR-0015 — but Pgvector implementation deferred. |
| **Primitives** | Two only: **Skill** (`SKILL.md`) and **Workflow** (`workflow.yaml` + inline persona). The separate **Agent** layer collapses into the Workflow's persona field. Subagent spawning deferred entirely. |
| **Workflows shipped** | Three: `default` (chat with persona + memory + optional `kb_search`), `flow-coach` (Vacanti + `gh_velocity`), `kb-qa` (librarian + `kb_search`). |
| **Workflow `co-planner`** | Deferred to v2 *unless* OQ-1 (calcmark API) resolves cheaply during P1. |
| **Memory** | Working memory (with 80% compaction + virtual files per Larson). Semantic memory (user facts, including agent-writeable "remember this"). Episodic and procedural memory rely on the existing file/DB structure but no automatic episodic-summary loop. |
| **KB sources** | **Hugo source repos only** (`dvhthomas/`, `calcmark/`, `alwaysmap/`). Drive folders, generic GitHub markdown, direct uploads, HTTP crawler — all deferred to v2. |
| **MCP tools** | Three: `gh_velocity`, `github` (read-only), `kb_search`. Each tool declares `action_category`; only `read` exists in v1. |
| **Auth** | Google OAuth for identity (single user). GitHub OAuth for the `github` and `gh_velocity` tools' tokens. **No other OAuth providers wired.** Token vault with Fernet encryption per ADR-0005 (per-run token cache). |
| **Approval gates** | **Simplified.** No `external_messaging`, no `irreversible`, no typed confirmation, no cooldowns. The two-category model: `read` (auto-allow) and `write` (always pause; click Approve in UI). The full five-category model is documented for v2. |
| **Budget caps** | **Per-session cap only** ($0.50 chat, $2.00 panel — but panel doesn't ship in v1, so effectively just $0.50). No per-day, per-month, kill switch, or user-level enforcement (single user). |
| **Inspection** | `/ui/runs` (basic list + timeline per run). |
| **Feedback** | **In v1.** 👍/👎 on every message and run, with optional comment. `run_feedback` table. |
| **Eval suite** | **In v1, but simple.** `data/evals/<workflow>/cases.yaml` + `kno eval <workflow>` CLI. No bump-level lint, no auto-eval-on-save (run eval manually). |
| **Refinement (`/admin/refine`)** | **In v1.** Pick workflow + 👎-filter → Claude proposes prompt diff → human approves → new version. **No rate limit** (single user; abuse is self-inflicted). |
| **Observability** | Structured logging, OTel scaffolding optional, daily integrity check on `kno.db` (NEW). |
| **Prompt injection defense** | **Hardened beyond v0.8.** Documented attack-pattern fixture set + LLM-as-judge defense scoring as part of P2 verification gate. |
| **Backup** | `kno backup` produces a tarball of `data/` (after `VACUUM INTO`); `kno restore` reverses. **In v1.** |
| **Git-backed data dir** | Deferred to v2. |
| **CLI** | Unified `kno` entry point per v0.8 (no `kno chat`, no `kno-cli`). |

### 2.2 What's deferred to v2

This is intentionally a long list. It captures all the work the spec accumulated that doesn't earn its place in a personal daily driver.

- **Multi-user**: allowlist enforcement, `UserScopedSession` (downgraded to be Phase-0-but-not-load-bearing-since-only-one-user), invite flow, isolation tests, per-user budget caps.
- **Panel of Experts**: entire `kind: panel` workflow type, panelist agents, integrator, structured-output panelist node, partial-panel failure handling, per-panelist drill-down.
- **Subagent runtime spawn mechanism**: deferred until a v2 workflow needs it.
- **Approval gate elaboration**: typed confirmation for `external_messaging`, cooldown for `irreversible`, `/admin/approvals`, per-user policy overrides, audit log views beyond the basic `audit_log` table.
- **KB sources beyond Hugo**: generic GitHub markdown, Google Drive folders, direct uploads (PDF/MD/TXT), HTTP crawler.
- **Multi-provider OAuth scaffolding**: Slack, Notion, Granola providers and connection management.
- **Refinement rate limit + bump-level lint**: defer the policy machinery.
- **Cost kill switch + per-day/month caps**: simple per-session cap is enough.
- **Git-backed `data/`** via `KNO_DATA_GIT_REMOTE`.
- **`PgvectorBackend` implementation**: only the `RetrievalBackend` Protocol interface ships in v1.
- **Agent primitive layer**: collapsed into Workflow.
- **DSPy** as an offline optimization tool.
- **Slack adapter** (the actual chat surface, not just OAuth).
- **Scheduled / webhook workflow triggers**.
- **Dashboards** (Larson's loop 4).
- **Cross-workflow eval batteries**.
- **Refinement dashboards** (aggregate analytics).
- **Token-key rotation playbook** (envelope encryption).
- **`coordinator: script` deterministic escape hatch**.

### 2.3 What's added or sharpened beyond v0.8

The "pi.ai play" framing surfaces things the team/corporate framing didn't emphasize. The first six come from "this is a daily driver, not a feature catalog." The last four were the adversarial audit's "what I'd add" list and apply even at Kno-Lite scope.

1. **Conversation persistence and resumption.** Every run has a `thread_id` (LangGraph already gives us this). `/ui/chat` shows the user's recent threads; clicking one resumes it with full context. The daily-driver experience is "pick up where I left off yesterday" — this matters more than the v0.8 spec treated it.
2. **Agent-writeable semantic memory.** A `remember_fact(key, value)` tool, `action_category: internal_write`, that lets the agent write to `semantic_facts` on its own. ("I learned Dylan prefers p85 over the mean — I'll remember that.") The owner can also write facts directly via `/ui/facts`.
3. **Daily-driver reliability checks.** Phase 0 verification adds: `PRAGMA integrity_check` cron, backup validity check, Ollama health probe (fail loud at boot, not silently at first query), Anthropic credentials probe at boot.
4. **Anti-loop / per-tool-call rate limit.** Inside a run: no tool may be called more than 10 times with semantically-equivalent args (hash check). Stops the runaway feedback loop that the per-session cost cap catches reactively.
5. **Citation integrity check.** Every `kb_search` chunk reference in agent output is validated against `kb_chunks` at render time. Hallucinated paths are flagged (red badge) in `/ui/chat`; the agent itself never sees the validation result (to avoid gaming).
6. **Prompt injection test battery.** A `tests/security/test_prompt_injection.py` fixture set with known attack patterns; LLM-as-judge scores resistance; run as part of Phase 1 (KB) verification gate.
7. **Token-vault rotation playbook (documented + tested even if rare).** Even at single-user scope, `KNO_TOKEN_ENC_KEY` is the single point of compromise for every connected OAuth token. v1 ships: envelope encryption (a fixed *KEK* in env wraps a per-row *DEK* in the column), a `kno rotate-keys` admin command that re-wraps every row under a new KEK, and a documented manual rotation playbook in `docs/ops.md`. The DEK-per-row approach means partial key compromise has limited blast radius.
8. **Data deletion / GDPR-style contract.** Even with one user, "let me wipe my own data" needs to work. v1 ships: `kno wipe --category <conversations|kb|semantic-facts|all> [--user me] --confirm` with explicit category model. Each category maps to a documented set of tables/files. Deletion is hard-delete; nothing is soft-archived. Documented in `docs/ops.md` so future-us (or v2 with real other users) inherits the contract.
9. **Anthropic-outage fallback usability test.** LiteLLM-to-Ollama failover (per ADR-0001) is configured for the **default chat workflow only** in v1. Phase 0 verification includes a manual "pull the Anthropic plug" test: kill Anthropic credentials, fire a default chat turn, confirm Ollama (`llama3.1-8b` or `llama3.1-70b` depending on host) produces *coherent* output, not just *any* output. If the fallback model is unusable in practice, the failover is theater and we fail Phase 0 honestly rather than ship a vapor feature.
10. **Cost-as-signal in agent state.** `AgentState.budget_remaining_usd` is a TypedDict field, populated at run start from the per-session cap minus prior cost. Agents can read it in their decision-making (a skill `cost-aware-reasoning` covers patterns like "I'm at $0.40 of $0.50 — skip the reflection step"). Reactive cost caps remain; this is the agent-side awareness on top.
11. **First-run experience: web-based setup wizard at `/setup`.** From a fresh clone: `clone → uv sync → uv run kno serve`. The server boots in **setup mode** (when critical secrets are missing from `.env`) and serves a multi-step HTMX wizard at `/setup` — all other paths redirect to it. The wizard walks every `.env` value step-by-step with **inline live validation**: paste Anthropic key → server hits Anthropic in real time → green check or red error inline. Same for Ollama probes, GitHub OAuth client verification, Google OAuth client verification. Generates Fernet KEK + session secret automatically. On completion, writes `.env` (mode 0600), runs alembic migrations, and reloads into normal mode. Resumable — half-completed setup persists across server restarts as `.env.partial`. **Two output modes**: local (writes `.env`) and Fly deploy (emits `fly secrets set ...` shell commands the user copies). Consistent with the v0.8 design principle: browser is canonical, CLI is a thin convenience. Costs ~1.5 dev-days; replaces the per-provider docs walkthrough as the *primary* setup path (the docs stay as reference / hand-edit fallback).
12. **Data portability: `kno export`.** `uv run kno export` produces a **human-readable** archive of your entire Kno history — conversations as markdown (one file per thread with timestamps, roles, inline tool calls), `semantic_facts.json`, `kb_sources/` with citation refs + reconstructed chunk text, `model_calls.csv` (your cost ledger), `feedback.json`, `connections.json` (provider list, **never** token values), plus the YAML/markdown of every workflow/agent/skill. Distinct from `kno backup` (opaque tarball for restoring Kno) — `kno export` is for reading your data outside Kno: archiving, grepping, importing to another tool, attaching to a thread elsewhere. Per-category like `kno wipe`. **Exit that doesn't trap you is the other half of "you depend on it."**

### 2.4 Phase compression

From 7 phases to **3 phases plus pre-flight**.

| Phase | Vertical | Demo gate | Calendar |
|---|---|---|---|
| **Pre-flight** | Foundation skeleton + OQ-2 resolution + dev env | — | 2–3 days |
| **0** (Foundation + Chat) | Project + DB + LangGraph + LiteLLM + Google OAuth + `/api/chat` + `/ui/chat` + default workflow + working & semantic memory + inspection + feedback rating + reliability checks | "Hey Kno, my name is Dylan. Remember that." → response. Tomorrow: "Who am I?" → "You're Dylan." | 2 weeks |
| **1** (KB + Flow Coach) | Hugo repo ingest + `kb_search` MCP + librarian persona + Flow Coach workflow + `gh_velocity` MCP + GitHub OAuth + citation integrity check + prompt injection test battery + eval suite + `kno eval` CLI | Ask Kno about a Bitsby post by topic → cited answer. "How is the kno repo doing?" → Vacanti-style answer. | 2–3 weeks |
| **2** (Refinement + Deploy) | `/admin/refine` end-to-end + backup/restore + Fly deploy + daily integrity check + final polish | 👎 a Kno response → `/admin/refine` proposes a fix → new version active → next response is better. Deployed at `kno.fly.dev`; pinned to Mac dock as a PWA. | 1.5–2 weeks |

**Total: ~6 weeks, single-developer.** Half the original 10-week plan, with the same daily-driver value proposition.

## 3. Consequences

### Positive

- **Ships in 6 weeks instead of 10.** More time spent on content (skills, prompts, eval cases, conversational tone) and less on infrastructure.
- **Genuinely tractable for one person.** Phase 0 is two weeks, not one. Pre-flight is real (resolve OQ-2, set up dev env, decide on a small set of seed skills).
- **The product is correctly framed.** "Daily-driver personal AI" has different success criteria than "corporate agentic system." Reliability beats breadth.
- **Adds reliability work that the team framing skipped.** Integrity checks, anti-loop, citation validation, prompt-injection battery — these are *more* important for a daily driver, not less.
- **All deferred work has a home.** v2 is a real roadmap, not a graveyard.

### Negative

- **Spec v0.8 partially "wasted."** Eight versions of careful design now have v2 stamps on some sections. Mitigation: the design work isn't wasted; it's the v2 reference. When we actually need multi-user, we have a tested-in-thought-experiment design.
- **Some risk of regret on Panel-of-Experts.** It's the most-fun-to-build, most-impressive-on-paper part of the spec. Resisting building it before there's a daily-driver Kno that's actually used takes discipline. Mitigation: scheduled "panel review" exercises in v2 planning will resurface it if it's still wanted.
- **Some elements of multi-user discipline get atrophied if not exercised.** `UserScopedSession` will still ship (one user), but the muscle of "always filter by user_id" won't be tested daily. Mitigation: ship the wrapper in Phase 0 anyway; future-us will thank present-us.

### Operational

- The full spec (`docs/spec.md` v0.9) gets a prominent "Kno-Lite v1 scope" callout linking to this ADR.
- `docs/plan.md` and `docs/tasks.md` get rewritten to reflect the 3-phase structure.
- Existing ADRs (0001–0017) remain valid; their applicability is scoped per this ADR (e.g. ADR-0010 multi-user isolation still ships the wrapper, but the dedicated isolation CI test is downgraded to "one-user smoke test" until v2).
- A future v2-scope-up ADR (when the time comes) explicitly references this one and re-activates deferred items.

## 4. Alternatives considered

### 4.1 Build the full v0.8 spec

10-week plan, 17 ADRs, multi-user, Panel, all OAuth providers, full approval gates.

**Rejected.** Adversarial audit showed this is over-engineering for a user base the owner hasn't named. The "team" framing is aspirational, not grounded. Building infrastructure for absent users is a recipe for unused features and unfinished polish.

### 4.2 Build nothing; use Claude Projects + Claude Code instead

The brutal honest version of "what's the dumbest thing that could work."

**Rejected** because the owner's stated aspiration is *to learn how to build, deploy, and refine* an agentic system. The learning is the point. Claude Projects + Claude Code is the right answer for "I want a working tool fast"; building Kno-Lite is the right answer for "I want to understand the substrate."

### 4.3 Build an even smaller "Kno-Tiny"

One workflow (default chat), one skill (cite-sources), no KB, no Flow Coach, no eval suite, no refinement page. Just chat + memory.

**Considered.** Rejected as *too* small: the feedback loop (eval + refine) is what makes Kno different from "any LLM chat with memory," and the KB is what makes Kno *yours*. Without those, Kno is barely a project.

Kno-Lite as scoped above is the smallest version that *teaches the full lesson*: harness, primitives, memory, retrieval, tool use, feedback loop, deployment.

### 4.4 Build the full spec but with deferred sections marked

Same scope as 4.1 but ship in slices, marking deferred items.

**Rejected.** This is what the existing plan already did, and the result was a 10-week plan with feature creep at every phase. Without a hard scope cut, the temptation to "just add the small thing" wins. ADR-0018 is the hard cut.

## 5. Reversibility

This ADR is **fully reversible** with a successor ADR. Specifically:

- Adding multi-user back (v2): re-activate the `UserScopedSession` enforcement; add the isolation CI test; build the invite flow. The schema already has `user_id` columns on everything; nothing data-shaped needs to change.
- Adding Panel: build `kno.workflows.kinds.panel` per the existing spec §9.4 + ADRs 0007/0008/0009. The state and checkpointer model already supports it.
- Adding more KB sources: implement against `Source` base class; backend doesn't change.
- Adding the `PgvectorBackend`: implement against the existing Protocol; flip `KNO_KB_BACKEND` env.

**Nothing about Kno-Lite forecloses on Kno-full.** This ADR scopes work, not architecture.

## 6. Verification

This ADR is satisfied when:
- [ ] `docs/spec.md` has a prominent "Kno-Lite v1 scope" callout linking to this ADR.
- [ ] `docs/plan.md` reflects the 3-phase structure (Pre-flight + Phase 0 + Phase 1 + Phase 2).
- [ ] `docs/tasks.md` reflects the cut task list.
- [ ] A memory entry records the scope decision so future-Claude doesn't re-propose the cut work.
- [ ] The user has approved the cut scope (this ADR was approved upon writing).

## 7. Open questions

- **When is "Kno-full v2" actually started?** The trigger should be a real second user (someone who is using Kno daily, not theoretically). Until then, every v2 feature is speculation.
- **Will the cut features pull back in incrementally?** ("Just one more thing.") That's exactly what scope creep is. The discipline: every cut feature requires its own ADR-to-add and a real user need.
- **What's the v2 prompt?** When v1 is shipped and exercised, the prompt for v2 won't be "build the rest of v0.8." It'll be informed by what daily use revealed needs. The v0.8 spec is a starting point, not a destination.
