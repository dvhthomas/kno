# ADR-0011: LangGraph SQLite checkpointer co-located with the app DB

**Status:** Accepted
**Date:** 2026-05-12
**Drafted in phase:** 0 (Foundation)
**Spec refs:** §4 (Tech Stack), §7 (Architecture), §11.5 (Migration sketch)
**Related ADRs:** [[0002]] (LangGraph state machine), [[0015]] (KB substrate)

---

## Context

LangGraph's `langgraph-checkpoint-sqlite` package writes graph-checkpoint rows to a SQLite database. Gulli's *Atlas Agents* shows the typical pattern (commit-message-paste from the user):

```python
checkpointer = SqliteSaver.from_conn_string("checkpoints.db")
```

— a *separate* `checkpoints.db` file from the application's own database.

Kno already runs SQLite for everything else: users, runs, messages, model_calls, semantic_facts, KB chunks (with sqlite-vec extension), workflows, etc. — all in a single `data/kno.db` file per [[0015]]. The question is whether the LangGraph checkpointer should live in:

- **(a) The same `kno.db` file** as the rest of the app.
- **(b) A separate `checkpoints.db` file** alongside.

This is a small decision but worth getting right at Phase 0 because reversing it later means dual-write migration of every in-flight checkpoint.

## Decision

**Co-locate.** LangGraph's checkpointer tables live in the same `data/kno.db` file as the rest of Kno's application schema.

Initialization at app boot:

```python
# src/kno/agent/checkpointer.py
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

def get_checkpointer() -> AsyncSqliteSaver:
    return AsyncSqliteSaver.from_conn_string(settings.database_url)
    # database_url = "sqlite+aiosqlite:///data/kno.db"
```

LangGraph auto-creates its own tables (`checkpoints`, `checkpoint_writes`, `checkpoint_blobs` — names may vary by minor version) on first use. Our Alembic migrations do **not** manage LangGraph's schema. The two coexist by table-name disjointness:

- **Our tables**: `users`, `runs`, `messages`, `tool_calls`, `model_calls`, `semantic_facts`, `kb_*`, `agents`, `workflows`, `skills`, etc. — managed by Alembic.
- **LangGraph tables**: `checkpoints`, `checkpoint_writes`, `checkpoint_blobs` (auto-created and auto-migrated by `langgraph-checkpoint-sqlite`).

If LangGraph adds a new table that collides with an Alembic-managed name in a future version, we surface that loudly (Phase 0 verification check enumerates expected tables and fails if either side moves) and resolve via either renaming our table or pinning the LangGraph version.

### Why one file

SQLite with WAL mode is highly capable for our usage profile:

- **Many concurrent readers + one writer** at a time. LangGraph writes are small (state diffs after each node) and short. Our application writes (creating a run, appending a message, ledger row) are similarly small. Lock contention isn't a concern at our request rate.
- **One file, one backup.** `cp data/kno.db data/kno.db.bak` is a complete snapshot. With WAL, also copy the `-wal` and `-shm` companions or run `VACUUM INTO` for a clean snapshot.
- **One volume mount on Fly.** No coordination required between volumes; no "what if checkpoints volume is unmounted but app volume isn't" scenario.
- **Identical migration story on move to Postgres.** [[0015]] migrates everything to Neon together — both `kno`-tables and the LangGraph checkpointer (via `langgraph-checkpoint-postgres`) live in the same Postgres database. The colocation principle holds across substrates.

### Connection management

LangGraph uses its own connection pool, distinct from SQLAlchemy's. Both connect to the same file. This is **fine in WAL mode** — multiple processes/pools sharing one SQLite WAL file is the explicit design.

Boot-time `PRAGMA journal_mode=wal` is set on the SQLAlchemy engine's first connection. LangGraph's connections inherit WAL because it's a file-level mode, not connection-level.

### Pragma settings (codified)

```python
# Applied via SQLAlchemy event listener on connect
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;        # WAL is durable enough with NORMAL
PRAGMA busy_timeout = 5000;          # 5s waiting before lock errors
PRAGMA foreign_keys = ON;
PRAGMA cache_size = -64000;          # 64MB negotiated cache (negative = KB)
```

These apply at the file level and are shared with LangGraph's connections.

### sqlite-vec extension co-loading

Per [[0015]], the `sqlite-vec` extension is loaded at connection time for KB retrieval. LangGraph's connections don't need it (LangGraph stores state as JSON blobs, not vectors), but they also don't conflict with it. The extension is loaded eagerly on every connection via a SQLAlchemy event listener; the small load overhead is acceptable.

## Consequences

### Positive

- **One file to back up, restore, copy, inspect.** `sqlite3 data/kno.db` is the universal entry point for any production debugging.
- **No connection-coordination surprises.** Both LangGraph and our app see the same data when the WAL flushes.
- **Migration to Postgres is structurally identical** — both schemas move to the same target DB.
- **Easier disaster recovery.** A point-in-time backup of one file captures everything Kno knows.

### Negative

- **Single point of failure.** If `kno.db` is corrupted, both app data and checkpoints are lost. Mitigated by WAL durability, Fly volume snapshots, and a daily backup-to-object-storage cron in v1.5 (deferred but tracked).
- **Schema collision risk.** If LangGraph adds a table with the same name as ours, we have to act. Mitigated by a verification check that enumerates table names at boot and asserts disjointness.
- **Writer contention** during a Panel run (5 panelists each producing checkpoint writes concurrently). Each individual write is <1ms in WAL mode; we expect no observable contention at typical loads. If we ever do see contention symptoms (busy timeouts in logs), we revisit.

### Operational

- **Backups**: `scripts/backup.py` runs `VACUUM INTO 'backup/kno-<ts>.db'` for a consistent snapshot. Cron'd daily on Fly.
- **`docs/ops.md`** documents the structure: which tables come from us (Alembic-tracked), which from LangGraph (auto-managed), how to inspect each.
- **Phase 0 verification** includes a check that lists all tables in `data/kno.db` after boot and asserts our + LangGraph expectations.

## Alternatives considered

### 1. Separate `data/checkpoints.db` file (the Gulli/LangGraph default example)

Run `SqliteSaver.from_conn_string("data/checkpoints.db")`.

**Rejected because:**
- Doubles the backup surface; two files to keep consistent for a restore.
- Doesn't reduce contention at our scale (WAL handles the load fine in one file).
- Doesn't simplify migration to Postgres — both files would still merge into one Postgres DB.
- Introduces a "which DB has what" cognitive overhead with no compensating benefit.
- The Gulli example is just an example; the LangGraph docs are fine with co-location.

### 2. In-memory checkpointer (`MemorySaver`)

Skip durable checkpointing.

**Rejected because:**
- §13 approval gates can outlive a process restart (user steps away, restart happens, user comes back next day to approve). In-memory loses this. **Non-negotiable.**

### 3. Redis-backed checkpointer

Use `langgraph-checkpoint-redis` with a Redis instance.

**Rejected because:**
- Extra service to deploy and monitor on Fly.
- Redis durability story is weaker than SQLite WAL for our values (every restart should resume cleanly; we'd need AOF and tuning).
- No payoff at our scale.

### 4. Postgres from day one (skip SQLite)

Run Postgres on Fly or Neon from v1; one shared DB for everything.

**Considered legitimately. Rejected for v1** because:
- Adds operational complexity (Fly Postgres or a Neon connection from day one).
- Spec A3 (SQLite + sqlite-vec) was a deliberate "simpler substrate wins" choice ([[feedback-prefer-simple-storage]]).
- The migration to Neon ([[0015]]) is mechanical when we need it; preempting that need isn't worth the cost.

### 5. Separate Postgres-only DB for checkpoints (hybrid)

SQLite for app, Postgres for checkpoints.

**Rejected.** No.

## Verification (Phase 0)

- **Smoke test**: build a 2-node LangGraph with `AsyncSqliteSaver.from_conn_string` pointing at `kno.db`; run; observe LangGraph tables auto-created in `kno.db`; restart the test process; resume the run from checkpoint; verify state intact.
- **Coexistence test**: run an Alembic migration that creates a new app table while LangGraph tables already exist; assert both side-by-side.
- **Disjointness assertion**: after first boot, enumerate all table names in `kno.db`; assert no collision between our Alembic-tracked set and LangGraph's set.
- **WAL pragma check**: `PRAGMA journal_mode` returns `wal` from both an SQLAlchemy connection and a LangGraph-internal connection.
- **Backup round-trip**: `VACUUM INTO 'kno.db.backup'`; remove original; restore from backup; both app data and an in-flight checkpoint are intact.

## Open questions deferred

- **Daily off-machine backup** to S3 / R2 / Tigris — deferred to v1.5; for v1 we rely on Fly volume snapshots.
- **Postgres migration ([[0015]])** — when triggered, both schemas move together. The Alembic migrations handle our tables; `langgraph-checkpoint-postgres` handles the checkpointer tables. No coordination logic needed beyond switching connection strings.
- **WAL companion file (`-wal`, `-shm`) handling** during snapshots — `VACUUM INTO` produces a clean DB file with no companions; that's the documented backup path. Direct file copy without checkpointing the WAL is unsafe; we don't expose that path operationally.
