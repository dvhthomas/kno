# ADR-0010: Multi-user data isolation via UserScopedSession + dedicated CI test

**Status:** Accepted
**Date:** 2026-05-12
**Drafted in phase:** 0 (Foundation; enforcement carries through every phase)
**Spec refs:** §3 (A1, A11), §11 (Memory — per-user scoping), §12 (Auth), §19 (Security Model — Threat 2)
**Related ADRs:** [[0001]] (LiteLLM gateway), [[0002]] (LangGraph state machine), [[0011]] (checkpointer colocation), [[0015]] (KB substrate)

---

## Context

Kno is multi-user (spec A1) — 3–10 trusted invitees plus the owner. Trust is *social*: I know these people. Trust is not *technical*: no user, however trusted, should be able to read another user's conversations, semantic facts, KB content, OAuth tokens, eval results, or refinement proposals.

The hardest part of multi-tenancy is consistency. The most common SaaS bug is "an engineer forgot a `.filter(user_id == current_user.id)` on one new endpoint and now user A can see user B's data." Industry reports show this is the single highest-frequency authorization vulnerability class.

Kno's architecture intentionally avoids structural mitigations like per-user databases (overhead doesn't justify the safety) and Postgres RLS (not applicable to our SQLite v1 substrate). What we have is **one shared SQLite file with `user_id` columns on user-scoped tables** — which puts the entire isolation burden on application-layer query construction.

This ADR addresses: how do we make "forget the `user_id` filter" structurally impossible, or at minimum impossible-to-miss in code review and CI?

Constraints:
- **SQLite (no RLS).** Postgres RLS is the obvious answer when it's available; it's not.
- **SQLAlchemy 2.x async** is the only DB access path.
- **A second invited user is a v1 release gate** (spec §21) — we ship the test, we exercise the test, we don't ship until the test is green.

## Decision

Adopt a **three-layer enforcement model**, all required:

1. **Type-level: `UserScopedSession` wraps `AsyncSession`** and injects `user_id` filters automatically on user-scoped tables.
2. **Test-level: a dedicated `test_isolation.py` integration test** creates user A and user B with distinct content across every user-scoped table, then exhaustively exercises every API endpoint as A and asserts no row of B's ever appears in any response. Same as B.
3. **Schema-level: a CI static check** verifies every new table with a `user_id` column is registered with the scoping wrapper, and every new API endpoint depends on `current_user` (not a path-param-derived user id).

Each layer catches a different failure mode; combined, they make isolation regressions near-impossible without an explicit, reviewable code change.

### Layer 1 — `UserScopedSession`

```python
# src/kno/db/session.py (sketch)
class UserScopedSession:
    """Wraps AsyncSession; injects user_id filter on user-scoped tables."""

    SCOPED_TABLES: ClassVar[frozenset[type[Base]]] = frozenset({
        Run, Message, ToolCall, ModelCall, SemanticFact, EpisodicSession,
        KBDoc, KBChunk, KBUpload, KBRepo, KBDriveFolder,
        ServiceConnection, RunFeedback, EvalRun, EvalCaseResult,
        RefineProposal, AuditLog,
    })

    def __init__(self, raw: AsyncSession, user: User):
        self._raw = raw
        self._user = user

    async def execute(self, stmt):
        rewritten = _inject_user_filter(stmt, self._user.id, self.SCOPED_TABLES)
        return await self._raw.execute(rewritten)

    # delegate add/delete/flush/commit to raw, but check table membership
    def add(self, obj):
        if type(obj) in self.SCOPED_TABLES and obj.user_id != self._user.id:
            raise IsolationViolation(...)
        self._raw.add(obj)
```

`_inject_user_filter` walks the statement's `FROM` clause, finds any scoped table without an explicit `user_id` filter, and appends `Table.user_id == self._user.id`. If a statement already has an explicit `user_id` filter, it's left alone (no double-filtering). A statement that joins two scoped tables gets the filter applied to both.

**API dependency injection** ensures every user-facing route receives a `UserScopedSession`:

```python
# src/kno/api/deps.py
async def get_db(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> UserScopedSession:
    return UserScopedSession(request.state.raw_session, current_user)
```

A separate `UnscopedSession` exists for admin paths and Alembic migrations — its use is **explicitly type-annotated** and CI flags any non-admin route that depends on it.

### Layer 2 — `test_isolation.py`

A pytest integration module that:

1. **Fixture**: spins up an ephemeral SQLite, applies all migrations, creates users `alice@example.com` and `bob@example.com`.
2. **Population**: as Alice, populates *every* user-scoped table with distinct fingerprint values (`run.title = "ALICE-RUN"`, etc.). Same as Bob with `BOB-`.
3. **Endpoint exhaustion**: introspects FastAPI's router; for every route whose path or operation_id implies user-scoped data, hits it as Alice; for `GET` endpoints, asserts no Bob-fingerprint string appears in any response body; for `POST/PATCH/DELETE` endpoints with body params, asserts Alice cannot reference a Bob-owned resource (e.g. POSTing feedback to Bob's `run_id` returns 403 or 404).
4. **URL-tampering tests**: explicitly tries hitting `/api/runs/<bob_run_id>`, `/api/workflows/<bob_private_workflow>`, `/api/kb/uploads/<bob_upload_id>` as Alice; asserts every one returns 403 or 404, never 200.
5. **Cross-user write tests**: asserts Alice cannot create a row with `user_id=bob.id` (the `UserScopedSession.add` check should raise).

The test is **non-skippable in CI**. Failure blocks merge.

A small route-registry fixture lists every user-scoped endpoint with its expected isolation behavior — so when someone adds a new endpoint, they must add it to the registry, which prompts thinking about isolation.

### Layer 3 — CI static checks

Two `pytest`-managed static checks in `tests/static/`:

1. **`test_scoped_table_registry.py`**: walks the SQLAlchemy metadata; any table with a `user_id` column must appear in `UserScopedSession.SCOPED_TABLES`. Fails the build on mismatch.
2. **`test_endpoint_uses_user_session.py`**: walks FastAPI's routes; any route whose handler signature includes a `Session` parameter must use `UserScopedSession`, not raw `AsyncSession` or `UnscopedSession` — unless the route is under `/admin/*` and explicitly tagged `requires_admin=True`.

These run on every PR.

### Non-user-scoped tables (visibility-controlled)

Some tables are not user-scoped because they're inherently shared or have a richer ownership/visibility model:

- `users`, `sessions` — admin-managed; read access controlled by route auth.
- `agents`, `agent_versions`, `workflows`, `workflow_versions`, `skills`, `skill_versions` — have `owner_id` + `visibility` (`owner_only`/`shared`/`org_default`). A separate **`VisibilityScopedSession`** wrapper enforces: `owner_id == user_id OR visibility != 'owner_only'`. Same three-layer enforcement applies (type wrapper + endpoint test + CI check).

The two scoping wrappers (`UserScopedSession`, `VisibilityScopedSession`) cover all of v1's user-touching data. Any new model must pick one or be admin-only.

### Admin override (audit-logged)

Admin support workflows occasionally need to "see what user X is seeing" — e.g. debugging a 👎 run or investigating a billing dispute. The mechanism:

- `/admin/impersonate/<user_id>` (admin only) starts an impersonation session with a 30-minute timeout.
- Every query during impersonation writes an `audit_log` row tagged `impersonation_active`.
- The owner sees a prominent UI banner "Impersonating <user_email>" with a one-click revoke.
- Impersonation cannot bypass approval gates — even as Alice, admin must approve Alice's pending actions.

## Consequences

### Positive

- **Forget-the-filter is impossible.** The `UserScopedSession` injects unconditionally. Engineers can't write `db.execute(select(Run))` and get all users' runs back — they get only the current user's by construction.
- **Isolation test is the v1 release gate.** Multi-user safety is verified empirically before deploy, not assumed.
- **Schema check catches drift** — new tables can't ship without explicit isolation classification.
- **Two wrappers cover the two patterns** (per-user vs visibility-controlled) so the rule set is small and learnable.

### Negative

- **Performance cost** — every query goes through filter injection. Benchmarked: ~50µs overhead per query on SQLite. Negligible at our request rate.
- **Boundary cases need careful handling.** Aggregations (`SELECT COUNT(*) FROM runs`) get the filter applied. Cross-table aggregations need explicit reasoning. The wrapper handles the common cases; complex queries should be reviewed.
- **VisibilityScopedSession is a second cognitive model.** Mitigated by: only two wrappers; clear docstrings; CI check forces explicit choice.
- **Impersonation is a new attack vector.** Mitigated by: admin-only, time-limited, audit-logged, UI-banner, doesn't bypass approval gates.

### Operational

- The two-user fixture in `tests/integration/conftest.py` is the canonical isolation test setup. New endpoints add coverage by extending its assertions.
- A weekly review of `audit_log` rows where `impersonation_active=true` is part of `docs/ops.md`.
- When a new scoped table is added, the migration PR must update `SCOPED_TABLES` or CI fails. Reviewer checklist explicitly calls this out.

## Alternatives considered

### 1. Manual `.filter(user_id == current_user.id)` everywhere

Trust developers to remember.

**Rejected because:**
- This is the #1 SaaS authorization bug. Industry data is unambiguous.
- The team is one person plus an LLM right now; the LLM will absolutely forget.
- Cost of the wrapper is small; cost of a leak is huge.

### 2. Postgres Row Level Security (RLS)

`CREATE POLICY` on every table.

**Rejected because:**
- We're on SQLite in v1 (per A3). RLS isn't available.
- On migration to Postgres (per [[0015]]), we can adopt RLS *in addition to* the wrapper — defense in depth. Documented as a v2 enhancement.

### 3. Per-user database files

Each user gets `data/users/<user_id>/kno.db`.

**Rejected because:**
- Shared resources (agents, workflows, skills) span users; they'd need a third "shared" DB.
- Backup, migration, cross-user analytics all become annoying.
- Doesn't solve the "wrong user_id in code" problem if the user_id is wrong elsewhere.

### 4. Schema-level prefixing (poor man's tenancy)

Prefix every table name with the user_id.

**Rejected because:**
- Migrations across all tenants become brittle.
- Schema bloat.
- Same fundamental problem (need to remember which table to read from).

### 5. Trust + code review

Skip the wrapper; rely on PR review to catch missing filters.

**Rejected because:**
- Code review catches some bugs and misses others. The cost of *one* miss is the entire isolation property.
- The wrapper is small. Just write it.

## Verification (Phase 0 + carried-through gate to v1)

- **Phase 0**: `UserScopedSession` exists; ScopedTable test enforces registration; UnscopedSession is used only in admin paths.
- **Every subsequent phase**: as new tables and endpoints land, the two-user fixture is extended; `test_isolation.py` runs green.
- **Phase 6 (release gate)**: `pytest tests/integration/test_isolation.py -v` is part of CI; failure blocks deploy. Manual URL-tampering attempt against the deployed `kno.fly.dev` confirms 403/404 for cross-user paths.

## Open questions deferred

- **Aggregate analytics** (e.g. "what's the median cost per run across all users?") — admin queries that need cross-user aggregation. Implementation pattern TBD when the first admin dashboard ships.
- **Workflow / agent sharing UX**: when a user marks an agent `shared`, what does the URL look like to a recipient? Path-param-derived user_id is risky — track in a future ADR when sharing ships.
- **Post-Postgres-migration RLS layer.** Add `CREATE POLICY ... USING (user_id = current_setting('app.user_id')::uuid)` to every table on top of the wrapper, for defense in depth. Track when [[0015]] migration triggers.
