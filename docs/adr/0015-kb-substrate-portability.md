# ADR-0015: KB substrate — SQLite + sqlite-vec + FTS5 for v1; `RetrievalBackend` interface for portable Postgres migration

**Status:** Accepted
**Date:** 2026-05-12
**Drafted in phase:** 2 (Knowledge Base) — pulled forward to Phase 0 because it's load-bearing for substrate decisions across the codebase
**Spec refs:** §3 (A3), §4 (Tech Stack), §10 (Knowledge Base), §11.5 (Migration sketch)
**Related ADRs:** [[0010]] (multi-user isolation), [[0011]] (checkpointer colocation)
**Memory refs:** [[feedback-prefer-simple-storage]]

---

## 1. Context

The KB is the part of Kno that lives or dies by retrieval substrate: a personal knowledge base of websites, PDFs, and Drive folders served back through agentic RAG with citations. Two design questions converge here:

1. **What do we store on (v1)?**
2. **What does it cost us to leave?**

Two concerns from the owner drove this ADR:

- "Postgres and SQLite, especially vector — are they truly interchangeable, or is 'mechanical migration' a comforting lie?"
- "If I have more than a single user, won't SQLite just break?"

The first question is real and partially valid: the spec's earlier "mechanical Alembic migration" wording oversold portability. The second is a widespread misconception about SQLite WAL semantics. Both deserve direct, numerical answers, and the answers need to live in a durable artifact so future-us doesn't relitigate.

This ADR also defines the abstraction that keeps the codebase honest about its own portability — without it, the spec's "we can migrate later" is hope, not architecture.

## 2. Decision

### 2.1 Substrate (v1)

Ship **SQLite (WAL mode) + sqlite-vec + FTS5** in `data/kno.db` for v1, in the same file as the rest of the app schema (per [[0011]]) and the LangGraph checkpointer (per [[0011]]).

Specifically:
- App tables via SQLAlchemy 2.x + Alembic migrations.
- Vector embeddings in a `kb_chunks` virtual table managed by `sqlite-vec` (loaded as an SQLite extension).
- Full-text search via SQLite FTS5 virtual table (`kb_chunks_fts`) mirroring `kb_chunks(fts_text)`.
- Retrieval = hybrid BM25 (FTS5) + cosine (sqlite-vec) merged via reciprocal rank fusion (RRF, k=60).

### 2.2 The `RetrievalBackend` interface (load-bearing)

Wrap every vector- and FTS-specific code path behind a Protocol. This is the only thing that touches substrate-specific query syntax. Everything else in the codebase sees the interface.

```python
# src/kno/knowledge/backends/base.py
from __future__ import annotations
from typing import Protocol, Sequence

from kno.knowledge.schema import Chunk, ScoredChunk


class RetrievalBackend(Protocol):
    """Abstraction over the (vector + FTS) substrate."""

    async def upsert_chunk(self, chunk: Chunk) -> None: ...

    async def delete_chunks_for_doc(self, doc_id: str) -> None: ...

    async def hybrid_search(
        self,
        query_text: str,
        query_embedding: Sequence[float],
        user_id: str,
        k: int = 8,
        source_kinds: list[str] | None = None,
    ) -> list[ScoredChunk]: ...

    async def health(self) -> dict[str, object]:
        """Cheap probe: returns {ok, vector_index_size, fts_index_size, ...}."""
        ...
```

Two implementations:

- **`SqliteVecBackend`** (v1): translates the protocol calls into `sqlite-vec` and FTS5 SQL.
- **`PgvectorBackend`** (migration target, written in the migration window but tested against a real Postgres in CI from day one): translates to pgvector + Postgres FTS.

Construction:

```python
# src/kno/knowledge/backends/__init__.py
def get_retrieval_backend(settings: Settings) -> RetrievalBackend:
    if settings.kb_backend == "sqlite_vec":
        return SqliteVecBackend(...)
    if settings.kb_backend == "pgvector":
        return PgvectorBackend(...)
    raise ConfigError(f"unknown kb_backend: {settings.kb_backend}")
```

The retrieval interface is the **only** thing `kno.services.kb`, `kno.mcp.servers.kb_search`, and `kno.knowledge.retrieve` see. **Migration day = swap the env var.** App code does not change.

### 2.3 Honest portability matrix

| Component | Verbatim portable? | Mechanism / notes |
|---|---|---|
| Business tables (`users`, `runs`, `messages`, `model_calls`, `tool_calls`, `service_connections`, `agents`, `workflows`, `skills`, `semantic_facts`, `audit_log`, etc.) | **Yes** | SQLAlchemy 2.x + Alembic. Common SQL surface. Verified in CI: same migrations run cleanly against both SQLite and Postgres test fixtures. |
| LangGraph checkpointer | **Yes (sibling package)** | `langgraph-checkpoint-sqlite` ↔ `langgraph-checkpoint-postgres`. Drop-in. |
| Encrypted token storage (`service_connections.access_token_enc` etc.) | **Yes** | `LargeBinary` column type. SQLite stores as `BLOB`; Postgres as `BYTEA`. |
| Timestamps | **Yes (with care)** | Stored as ISO-8601 strings in v1 to avoid SQLite's lack of native `TIMESTAMP WITH TIME ZONE`. Portable. |
| JSON columns (`runs.metadata`, `eval_case_results.judge_output`, `kb_drive_folders.files_state`) | **Mostly** | Storage portable; **indexing on JSON paths is not.** SQLite can't `CREATE INDEX ON ((data->>'key'))`. If we ever need to query JSON paths fast, we'll need a conditional Alembic migration. Today we don't. |
| Boolean columns | **Yes** | SQLite stores as 0/1; SQLAlchemy normalizes. |
| **Vector embeddings storage** | **NO — behind `RetrievalBackend`** | sqlite-vec: virtual table `vec0(embedding float[768])`. pgvector: `vector(768)` column. Storage shape differs. |
| **Vector similarity query** | **NO — behind `RetrievalBackend`** | sqlite-vec: `SELECT id, distance FROM vec0_table WHERE embedding MATCH ? ORDER BY distance LIMIT 8`. pgvector: `SELECT id, embedding <=> ?::vector AS distance FROM table ORDER BY distance LIMIT 8`. Not query-compatible. |
| **Approximate-NN index** | **NO** (sqlite-vec is brute-force only as of current version) | pgvector adds HNSW (`USING hnsw (embedding vector_cosine_ops)`) and IVFFlat. The reason to migrate at high chunk counts. |
| **Full-text search storage** | **NO — behind `RetrievalBackend`** | SQLite: `FTS5` virtual table. Postgres: `tsvector` column + `GIN` index. |
| **Full-text search query** | **NO — behind `RetrievalBackend`** | SQLite: `MATCH 'query'`. Postgres: `tsvector_col @@ to_tsquery('query')`. Not query-compatible. |
| **Hybrid retrieval (BM25 + vector + RRF)** | **NO — behind `RetrievalBackend`** | The merge logic talks to both indices; both indices differ. RRF formula is portable; the score sources are not. |
| **Concurrent write semantics** | **Behavioral difference, hidden by SQLAlchemy** | SQLite WAL: one writer queued; readers don't block. Postgres MVCC: real concurrent writers. Application code should not depend on either. CI integration test asserts: no `BEGIN IMMEDIATE` followed by long-running work outside a transaction. |

**Summary**: ~70% of the database surface area is verbatim portable. The other ~30% (vector + FTS + hybrid retrieval) goes through one Protocol with two implementations. The retrieval interface is small (4 methods); the SqliteVec implementation is ~200 LOC; the Pgvector implementation is similar.

### 2.4 Multi-user concurrency reality check

The "SQLite breaks at multi-user" misconception comes from confusing **SQLite default mode** (whole-DB lock during a writer transaction; readers blocked) with **SQLite WAL mode** (writers serialized but readers unblocked).

In WAL mode, on modern hardware, SQLite handles:

- **~1,000–5,000 small write transactions per second** sustained.
- **Tens of thousands of concurrent readers** without contention (each gets a consistent snapshot).
- **One writer at a time** — writes serialize through a single file lock, queued not blocked.

Kno's actual write profile at 10 concurrent users at peak chat rate:

| Workflow | Writes per turn | Turns per active user/min |
|---|---|---|
| Chat (flow-coach, kb-qa, co-planner, default) | ~12 (1 run + 1 message + 3 model_calls + 1 tool_call + ~5 LangGraph checkpoints + 1 audit row) | ~2 |
| Panel (program-review-panel) | ~40 (parent + 5 child runs + ~20 model_calls + ~10 tool_calls + checkpoints) | ~0.5 |
| KB ingest (background) | ~1 write per chunk; ~50–500 chunks per source | sporadic |

Worst case I can construct: 10 users all firing simultaneous panels = ~400 writes within ~10s = **~40 writes/sec**. SQLite WAL is at ~1–4% of capacity.

**The objective triggers to migrate to Postgres** are:

| Trigger | Why |
|---|---|
| > 30 concurrent active users producing chat or panel runs | Writer-lock contention starts to be observable in p99 latency |
| Multi-region deployment for latency | SQLite can't replicate across regions; Postgres + Neon read replicas can |
| Total KB chunks > 500,000 | sqlite-vec is brute-force; pgvector HNSW becomes worth the migration for sub-100ms p99 retrieval |
| Need > 1 app machine behind a load balancer for redundancy | Two machines cannot safely share one SQLite file; one needs to be the writer-master and the others read replicas, but SQLite doesn't natively replicate |
| KB grows past ~50GB total file size | SQLite is still fine but operationally awkward (backup time, VACUUM cost) |

**The non-triggers**:

- Adding user #2 through user #30 — well within SQLite's envelope.
- KB grows from 1k to 100k chunks — sqlite-vec handles brute-force search at this size in sub-second; HNSW unnecessary.
- Adding more workflow definitions, more agents, more skills — these are tiny.
- A long-running session with deep memory — working memory compaction (§11.1) keeps state-size bounded.
- A burst of approval-gated runs with hours of pending state — checkpoints are small; SQLite handles state-at-rest trivially.

**The pre-trigger discipline** (to make sure we notice before we hurt):

- Phase 6 ships a `/admin/ops` page surfacing `vector_index_size`, `fts_index_size`, `active_users_24h`, `writes_per_second_p95`, `writer_lock_wait_p99_ms`. The metrics are read directly from `backend.health()` and ledger queries.
- A weekly `/admin/ops` review is in `docs/ops.md`. If any trigger metric approaches 50% of its threshold, plan the migration window.

### 2.5 Migration playbook (tested at the end of Phase 2)

When triggered, the move is **1–2 days of focused work**:

| Step | What | Approximate effort |
|---|---|---|
| 1 | Stand up Neon Postgres, enable `pgvector` extension, `CREATE DATABASE kno` | 30 min |
| 2 | Update `KNO_DATABASE_URL` env var to point at Neon | 1 min |
| 3 | Run `uv run alembic upgrade head` against Postgres. SQLAlchemy normalizes our types; same migration files succeed. | 15 min |
| 4 | Set `KNO_KB_BACKEND=pgvector` env var. `PgvectorBackend` is already implemented and CI-tested; the constructor wires up. | 5 min |
| 5 | **Data export from SQLite, import to Postgres.** App tables via `pgloader` or a small script using SQLAlchemy. Embeddings need re-embedding *only if* the storage format changes meaningfully between sqlite-vec's blob layout and pgvector's `vector(768)` — in practice we re-embed by replaying the existing chunk text through `Ollama.embed` (cheap, deterministic, $0 cost since Ollama is local). | 4–8 hours wall time for a 100k-chunk KB |
| 6 | Run the multi-user isolation test against the new substrate (per [[0010]]). | 30 min |
| 7 | Run the eval suite against every workflow to confirm retrieval quality regression-free. | 1 hour |
| 8 | Switch traffic by deploying the new env vars. Keep SQLite file as backup for 30 days. | minutes |

Steps 1–4 are reversible at any point by toggling `KNO_KB_BACKEND` and `KNO_DATABASE_URL` back. Steps 5+ are forward-only after the export window closes.

**Why this isn't "weeks":** because we never wrote SQLite-specific code outside of `SqliteVecBackend`. The retrieval interface contract is what makes this honest.

### 2.6 Implementation rules (enforced)

- **Nothing in `kno.services.*`, `kno.agent.*`, `kno.workflows.*`, `kno.mcp.*` imports `sqlite-vec` or `pgvector` directly.** They only see `RetrievalBackend`. Enforced by a static CI check (similar to [[0001]]'s anthropic-direct restriction).
- **`SqliteVecBackend` and `PgvectorBackend` both ship from Phase 2.** The Pgvector implementation is not a "future ADR" — it lives in `src/kno/knowledge/backends/pgvector.py` from day one and is exercised in a Postgres-backed CI integration test (small `pytest-postgresql` fixture). If we ever can't keep both implementations green, we know immediately, not at migration time.
- **The hybrid-search RRF logic lives in `RetrievalBackend` implementations**, not in `kno.services.kb`. Both implementations produce `ScoredChunk` with identical schema; the service layer is substrate-agnostic.
- **CI matrix runs the KB test suite against both backends.** Phase 2 verification gates on this.

## 3. Consequences

### Positive

- **Migration is honest.** "1–2 days, swap an env var, re-embed" is verifiable, not aspirational. We've actually built the Pgvector implementation in v1 — it's not a future-us problem.
- **The trigger criteria are objective.** Future-us has measurable thresholds, not gut feel. The `/admin/ops` page surfaces them.
- **The misconception is buried.** "SQLite breaks at multi-user" is contradicted by the numbers in §2.4. Anyone re-asking gets pointed at this section.
- **Interface discipline pays elsewhere too.** The same `RetrievalBackend` Protocol could be backed by an entirely different store in v2 (Qdrant, Vespa, Turbopuffer) without touching consumer code — even though we don't intend to.

### Negative

- **Two backends to keep green.** Pgvector tests in CI add ~30s to the suite. Worth it.
- **Re-embedding on migration takes hours.** Mitigated by Ollama being local + free; not a budget concern, just wall time.
- **Some optimizations that would be SQLite-native (e.g. STORED virtual columns for FTS-trigger-driven sync) are kept generic.** Modest performance trade-off; well within budget.
- **The `RetrievalBackend` interface is a real abstraction**, which means designing it. We accept this; the alternative (no abstraction) is the comfortable lie this ADR exists to refuse.

### Operational

- The Phase 2 verification gate includes: "Pgvector backend passes the same retrieval-quality eval cases as sqlite-vec, on a containerized Postgres in CI."
- `/admin/ops` surfaces the trigger metrics; weekly review per `docs/ops.md`.
- On the day we migrate, we run [[0010]]'s isolation test against Postgres. Multi-user safety is asserted on the new substrate before traffic flips.

## 4. Alternatives considered

### 4.1 Postgres from day one

Skip SQLite; deploy Neon Postgres + pgvector immediately in v1.

**Rejected** — but it's a defensible choice, just not ours.

For:
- Eliminates the migration risk entirely.
- HNSW indexing available immediately if KB grows.
- One substrate, one mental model.

Against:
- Adds operational complexity in v1 (separate DB service to manage, even on Neon).
- $5–15/mo recurring cost for an empty database during early dev.
- Loses the "single-file, single-volume, copy-to-back-up" simplicity that the local-on-laptop deployment mode (spec §1) leans on.
- The migration is documented and tested — "future cost" is bounded.
- [[feedback-prefer-simple-storage]] explicitly favors the simpler substrate first.

**This is the strongest "should we reconsider in 6 months" candidate.** If we end up with a hosted-Fly-only deployment and the local-on-laptop mode loses importance, the trade-off shifts. Track as an OQ.

### 4.2 SQLite for app, separate vector DB (Qdrant / Chroma) for embeddings

Hybrid: business tables in SQLite, vectors in a dedicated vector service.

**Rejected** because:
- Adds a service to deploy.
- Eliminates the "one file" backup story.
- The retrieval interface trick already lets us swap *just* the vector substrate without committing to a separate service in production.
- At our scale, sqlite-vec is fast enough; the only reason to split would be HNSW, which means we should just move to Postgres + pgvector together.

### 4.3 Pure SQLite (no abstraction)

Just write SQLite + sqlite-vec calls everywhere; deal with migration when we have to.

**Rejected** because:
- This is what the spec's earlier wording oversold. Honest migration would be "rewrite every retrieval call site" — possibly weeks of work, definitely more risk than necessary.
- The interface is small (4 methods); writing it costs less than not writing it.

### 4.4 Pure file-on-disk + numpy (no DB engine for vectors)

Embeddings in `.npy` files; FTS via `whoosh` or similar.

**Rejected** because:
- Loses transactional guarantees on the chunk→embedding relationship.
- No incremental indexing — every upsert rewrites the array.
- Multi-user safety becomes file-locking gymnastics.
- sqlite-vec gives us most of the simplicity advantages with none of these drawbacks.

### 4.5 Turso (libSQL — SQLite-with-replication)

Embedded-Replicas SQLite with Turso's hosted layer.

**Rejected for v1** because:
- Adds a hosted dependency.
- Doesn't help with the hard problem (vector scale).
- Worth revisiting if cross-region read replicas become a goal.

### 4.6 DuckDB

Columnar embedded database with strong analytics.

**Rejected** because:
- Strong analytics, weak OLTP. Our workload is OLTP (lots of small writes, point lookups, occasional aggregates).
- Vector support is newer and less battle-tested than sqlite-vec or pgvector.
- Would require its own `RetrievalBackend` implementation; no compensating benefit.

## 5. Verification (Phase 2 verification battery)

- **Unit test**: `RetrievalBackend` interface is satisfied by both `SqliteVecBackend` and `PgvectorBackend` (Protocol conformance check).
- **Integration test (CI matrix)**: KB ingest + retrieve pipeline runs end-to-end against `SqliteVecBackend` (default) and `PgvectorBackend` (`pytest-postgresql` fixture). Identical assertions against both. **Required green.**
- **Migration dry-run test (Phase 2 verification)**: synthetic 1,000-chunk dataset is exported from SQLite, imported to Postgres, re-embedded, retrieved with the same queries; result sets are equivalent (top-K overlap ≥ 90%, all citations resolve).
- **Static check**: no module outside `kno.knowledge.backends.*` imports `sqlite_vec`, `pgvector`, or `psycopg.types.range` (a proxy for "you're talking to Postgres directly"). CI fails on violation.
- **Concurrency test**: 10 simulated concurrent writers each upserting chunks while 20 concurrent readers issue `hybrid_search`; no deadlocks, no isolation violations; p95 search latency stays under 200ms with 25k chunks.
- **Trigger-metric test**: `/admin/ops` endpoint returns plausible values for all five trigger metrics; values change as the DB grows in a fixture test.

## 6. Open questions deferred

- **Should we ship a "small Postgres" option in v1?** (e.g. SQLite for solo deploys, Postgres for invitee deploys.) Defer until at least one invitee deployment exists; the substrate decision is per-deployment anyway via env var.
- **Backup format on migration day** — `VACUUM INTO` snapshot of the SQLite file, retained 30 days, or `pg_dump` of the post-migration Postgres for a known good point? Both, probably. Documented at migration time, not pre-resolved here.
- **Re-embedding cost projection** — at 1M chunks, Ollama on a Fly machine would take ~3 hours wall time for re-embedding. Acceptable but worth flagging if the KB grows past that.
- **Schema versioning for the `RetrievalBackend` Protocol itself** — when we add a 5th method (e.g. `delete_user_chunks` for GDPR), both backends update. Track as a normal API-change discipline; no special mechanism needed at our scale.
