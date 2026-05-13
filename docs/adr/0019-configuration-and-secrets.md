# ADR-0019: Configuration & secrets — four-tier model with one credentials table

**Status:** Accepted
**Date:** 2026-05-12
**Drafted in phase:** 0 (Foundation; design decision before code)
**Spec refs:** §3 (A3, A13), §4 (Tech Stack), §12 (Auth & Connections), §6 (Project Structure)
**Related ADRs:** [[0001]] (LiteLLM gateway), [[0005]] (per-run decrypted-token cache), [[0010]] (multi-user isolation), [[0011]] (checkpointer colocation), [[0018]] (Kno-Lite scope)

---

## 1. Context

The Kno codebase needs to handle several distinct kinds of "configuration." They tend to get conflated in discussions ("just put it in env") but they have genuinely different lifecycles, audiences, and trust profiles. Conflating them produces three failure modes:

1. **The "deploy to add a Jira" problem**: putting per-user integration credentials in env means every new integration is a redeploy. For an agent harness whose value is in user-configured integrations, this is fatal.
2. **The "where does the URL go" problem**: a Jira integration needs both a credential (API token) and config (the Jira URL, project key). Storing the token in DB and the URL in a YAML file is needlessly split. Storing both in env multiplies the deploy problem.
3. **The "I forgot which user's token" problem**: at scale (or even at 2 users), a global env var for "the Jira token" doesn't work. Credentials are per-user.

The owner raised this question explicitly during pre-flight:

> "It uses the `gh` command handling of GitHub repos. I have no idea how that'd work for Jira examples. Maybe there's a token for that? Regardless, we need a way to configure 'settings' like this in Kno (DB secrets table? 12-factor app?)"

This ADR establishes the four-tier model and the schema extensions needed to make it work, including for v1 Kno-Lite even though v1 only exercises two of the four tiers actively.

## 2. Decision

Kno has **four configuration tiers**, each with a clear home, audience, and lifecycle:

| Tier | Lives in | Audience | Lifecycle |
|---|---|---|---|
| **Bootstrap** | `.env` (12-factor) | Operator (the person who deploys) | Restart-required |
| **User credentials & integrations** | DB table `service_connections` | The owner (and future users) via `/ui/connections` | Hot — UI add/edit/revoke |
| **Behavior config** | YAML / markdown files under `data/` | The owner (Dylan editing prompts and rules) | Hot — `POST /api/data/reload`; or git-backed with `KNO_DATA_GIT_REMOTE` (v2) |
| **Agent memory** | DB tables `semantic_facts`, `episodic_sessions` (v1.5), `messages` | The agent itself + the user via `/ui/facts` | Continuous |

### 2.1 Bootstrap (`.env`)

Things the FastAPI server needs to *start*. Per-server, restart-required, secrets-grade.

Required:
- `KNO_ADMIN_EMAIL`
- `KNO_TOKEN_ENC_KEY` (Fernet KEK)
- `KNO_SESSION_SECRET` (HMAC for cookies)
- `KNO_GOOGLE_CLIENT_ID` + `KNO_GOOGLE_CLIENT_SECRET` (Kno's *own* OAuth registration with Google — not a user's token)
- `KNO_GITHUB_CLIENT_ID` + `KNO_GITHUB_CLIENT_SECRET` (same for GitHub)
- `KNO_ANTHROPIC_API_KEY` (Kno's organizational key; all users' inference goes through it; per-user budget enforcement lives in DB)
- `KNO_OLLAMA_BASE_URL`, `KNO_OLLAMA_EMBED_MODEL`, `KNO_OLLAMA_FALLBACK_CHAT_MODEL`
- `DATABASE_URL`
- `KNO_HOST`, `KNO_PORT`

Optional:
- `KNO_HONEYCOMB_KEY`, `KNO_HONEYCOMB_DATASET`
- `KNO_LOG_LEVEL`, `KNO_LITELLM_LOG_LEVEL`
- `KNO_DEV_MODE`, `KNO_EVAL_USE_REAL_LLM`

**Anti-rule for this tier**: per-user credentials never live here. `KNO_ALICES_JIRA_TOKEN` is structurally wrong.

### 2.2 User credentials & integrations (`service_connections`)

**One table, two patterns** — OAuth and API-token — distinguished by a `connection_kind` enum.

```sql
CREATE TABLE service_connections (
    id                  INTEGER PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    provider            TEXT NOT NULL,        -- 'google', 'github', 'jira', 'linear', ...
    connection_kind     TEXT NOT NULL,        -- 'oauth' | 'api_token' | 'none'
    connection_label    TEXT NOT NULL,        -- user-facing name, e.g. "Personal Jira"
    access_token_enc    BLOB,                 -- Fernet-encrypted
    refresh_token_enc   BLOB,                 -- Fernet-encrypted (oauth only)
    token_expires_at    TIMESTAMP,            -- (oauth only)
    scopes              TEXT,                 -- comma-separated string
    config_json_enc     BLOB,                 -- Fernet-encrypted JSON for extra non-secret config
                                              -- (Jira URL, project key, default board, etc.)
    created_at          TIMESTAMP NOT NULL,
    last_used_at        TIMESTAMP,
    revoked_at          TIMESTAMP,
    UNIQUE(user_id, provider, connection_label)
);
```

**The `(user_id, provider, connection_label)` unique constraint is load-bearing**: it allows a single user to have N connections to the same provider (e.g. multiple Google accounts). See §2.5 for the UX implications.

**Why `config_json_enc` is also encrypted** even though some fields aren't secret (Jira URL): it simplifies the threat model (one decryption path; nothing to forget); doesn't meaningfully add cost; future-proofs against fields that *do* become sensitive (some Jira fields shouldn't leak).

**Pattern 1 — OAuth provider** (Google, GitHub, future Slack/Notion/Granola):
- `connection_kind = 'oauth'`
- `access_token_enc`, `refresh_token_enc`, `token_expires_at`, `scopes` all populated
- `config_json_enc` typically empty
- `/ui/connections` shows a "Connect with X" button → standard OAuth flow

**Pattern 2 — API-token provider** (Jira, Linear, generic webhook-style services):
- `connection_kind = 'api_token'`
- `access_token_enc` holds the PAT
- `refresh_token_enc`, `token_expires_at` empty
- `config_json_enc` holds the URL, project key, email (for Atlassian Basic Auth), etc.
- `/ui/connections` shows an "Add <provider>" form requesting the fields

**Pattern 3 — Configuration-only** (`connection_kind = 'none'`):
- For integrations that need configuration but no credential (e.g. "default branch for this repo"). Rare; reserved.

### 2.3 Behavior config (`data/`)

Workflow definitions, agent personas, skills, evals, policy, allowlist. **Filesystem-as-truth** per ADR-0018; markdown + YAML; git-friendly; owner-edited.

Tool-specific behavior config (default windows, format preferences) lives in the **workflow YAML** under a `tools.<name>.config` block:

```yaml
# data/workflows/flow-coach/workflow.yaml
name: flow-coach
kind: chat
persona: persona.md
tools:
  allow:
    - mcp:flowmetrics
    - mcp:github
    - mcp:kb_search
    - mcp:remember_fact
  config:
    flowmetrics:
      default_since: "30d"
      default_format: json
      forecast_simulations: 10000
```

The MCP server's tool implementation reads from this block. If absent, sensible defaults apply.

**Why not put tool config in `service_connections.config_json`?** Two different scopes:
- Tool config in workflow YAML = "how Flow Coach uses flowmetrics" (per-workflow, version-controlled, diff-friendly).
- `service_connections.config_json` = "where Alice's Jira lives" (per-user, per-connection, secret-adjacent).

Different audiences, different lifecycles, different storage.

### 2.5 Multiple connections per (user, provider) — load-bearing

The schema unique constraint is `UNIQUE(user_id, provider, connection_label)` — **not** `(user_id, provider)`. This is intentional and load-bearing for the use case the owner described: "Kno app that can read my Google Drive stuff from *multiple* Google accounts."

A user can have N connections to the same provider, each with a distinct user-chosen label:

```
service_connections
─────────────────────────────────────────────────────────────────
user_id  provider  connection_label       access_token_enc   ...
─────────────────────────────────────────────────────────────────
dylan    google    "Personal"             Fernet(...)
dylan    google    "Work"                 Fernet(...)
dylan    google    "Side project"         Fernet(...)
dylan    github    "Personal"             Fernet(...)
dylan    github    "Work (alwaysmap)"     Fernet(...)
dylan    jira      "Work — Atlassian"     Fernet(...)
```

**The `/ui/connections` UX is "Connect Google" / "Connect GitHub" as a button you can press repeatedly**. Each press runs a fresh OAuth flow (the provider's consent screen lets the user pick which account; Google + GitHub both support this natively). On callback, the user is asked for a `connection_label` (with a sensible default proposed from the OAuth profile's `email`/`name` field).

Provider-side:
- **One OAuth app registration** per provider, configured in `.env` (`KNO_GOOGLE_CLIENT_ID`/`SECRET`, `KNO_GITHUB_CLIENT_ID`/`SECRET`). The app declares all scopes Kno might ever want for that provider; the user grants what they grant per-account.
- **The app's callback URL** matches the deployment (`http://localhost:8000/api/auth/<provider>/callback` for local, `https://kno.fly.dev/api/auth/<provider>/callback` for hosted). Both are registered as authorized redirect URIs in the OAuth client config.
- **Scopes are declared per-provider in code** (`src/kno/auth/providers/<name>.py`), not in `.env`. They're part of Kno's identity, not deployment config.

#### Connection selection: per-workflow checkboxes (layered authority)

When a user has multiple connections to a provider and a workflow uses that provider, **the workflow's configuration declares which connection(s) are permitted**. The user ticks 1+ boxes per provider in the workflow's settings UI. Within that ticked set, the agent decides at tool-call time which to use for a specific call.

This is **layered authority**: user sets the permitted set; agent selects within it. The agent has no path to a connection the user didn't tick.

##### Storage — workflow YAML

```yaml
# data/workflows/flow-coach/workflow.yaml
name: flow-coach
kind: chat
persona: persona.md
tools:
  allow:
    - mcp:github
    - mcp:flowmetrics
    - mcp:kb_search
    - mcp:remember_fact
  connections:
    # Per-provider list of connection_labels permitted for this workflow.
    # Optional; absent means "all of the user's connections for the
    # provider are eligible" (the v1 default since users only have one
    # each).
    github: ["Personal"]
```

##### UI — `/ui/workflows/<slug>` edit page

For each MCP server in `tools.allow` that requires a provider connection, the form shows a `<fieldset>` listing the user's authorized connections for that provider with checkboxes. The user ticks 1+. Saved to `tools.connections[provider]` in the workflow YAML; workflow version bumped per the standard save flow.

```
☑ mcp:github
    Available GitHub accounts:
     ☑ Personal       (last used 1h ago)
     ☐ Work — alwaysmap
     [ + Connect another GitHub account ]
```

A separate `[ + Connect another <provider> account ]` link opens the standard `/ui/connections` OAuth flow with a banner "connecting will return you here." After the new connection is saved, the user is bounced back to the workflow edit page with the new account appearing as an unchecked checkbox.

##### Resolution rule at tool-call time

The MCP host receives a tool call from a workflow's run. Resolves the connection set:

1. If `workflow.tools.connections[provider]` is set: agent may only use connections whose `connection_label` is in that list.
   - Single label in list → use that connection.
   - Multiple labels in list → agent picks (typically by passing `connection_label` as a tool argument the synth node populates; tools that legitimately want all-of fan out themselves).
2. If `workflow.tools.connections[provider]` is absent → all of the user's connections for that provider are eligible. Same selection logic within the eligible set.
3. If the eligible set is empty for a required provider → tool returns a clear error: `"no <provider> account selected for this workflow; tick one in workflow settings at /ui/workflows/<slug>"`. Agent surfaces verbatim to the user.

##### v1 vs v2 split

| Concern | v1 (Kno-Lite) | v2 |
|---|---|---|
| Schema (`tools.connections` in YAML) | Ships | Same |
| Resolution logic in MCP host | Ships (works with single connection too) | Same |
| UI: `<fieldset>` per provider | Ships **as a single dropdown** (v1 has one connection per provider) | Becomes a checkbox group |
| `[ + Connect another <provider> account ]` link | Hidden in v1 | Visible |
| Per-chat override (one-conversation alternate selection) | Out of scope | Reserved as an OQ |

The v1 single-connection world makes the UI vacuous (one box, default-checked). The data model is correct from day one; when v2 enables multi-account UX, the UI lights up without a schema migration.

##### Why this is simpler than the alternatives

- **No "tool argument" contract creep.** Tools that need a `connection_label` arg get it from the run's resolved set; the agent doesn't have to invent it.
- **No MRU heuristic.** No "but it picked the wrong one" debugging.
- **No agent-asks-for-clarification.** The workflow's ticks are the answer.
- **Fan-out is opt-in per tool.** Tools that semantically want all-of (like a cross-account KB search) iterate the resolved set themselves; tools that don't always pick.

##### Reserved OQ: per-chat override

A small UI affordance — a connection-set dropdown at the top of `/ui/chat` letting the user override the workflow's defaults for *this conversation only* (no workflow version bump). Useful pattern: "ask Flow Coach about Work just this once." Not in v1 scope; tracked as a v2 follow-on. Will surface naturally if/when daily use produces the "I keep editing the workflow and switching it back" annoyance.

### 2.6 Agent memory (`semantic_facts`, future `episodic_sessions`)

Not config — long-term agent state. Mentioned here only because it's sometimes confused with config:

- *"Remember that I prefer P85 over the mean"* = `semantic_facts`. Written by the agent (via `remember_fact` tool) or the user (via `/ui/facts`).
- *"Use a 60-day window when I ask about kno"* = could be a `semantic_facts` row that flow-coach's persona instructs it to read, OR a workflow YAML default. Default: ask the user once, store the answer as a fact. Don't bake into YAML — too rigid.

## 3. flowmetrics-specific note (per `docs/notes/gh-velocity.md`)

flowmetrics needs GitHub authentication. It uses `gh` CLI which honors `GH_TOKEN` env var. So:

- **No new `service_connections` row needed.** flowmetrics reuses the **existing GitHub OAuth connection** for the requesting user.
- The flowmetrics MCP server (Phase 1 task 1.9):
  1. Calls `tokens.get_or_decrypt(run_id, "github")` (per ADR-0005 cache).
  2. Spawns `uv run flow ...` subprocess with `env={"GH_TOKEN": <decrypted>, ...minimal-allowlist}`.
  3. Subprocess's internal `gh` calls authenticate via `GH_TOKEN`. No `gh auth login` required on the host.

This is the v1 pattern. **No env var, no new table row, no new UI form.** The Kno-Lite v1 scope therefore touches only Tiers 1 + 2 (OAuth-only) actively; Tier 2's API-token branch ships in the schema but no UI populates it until v2.

## 4. Jira (future v2) walk-through

The reference scenario for "what does this look like for a future API-token integration."

1. **User goes to `/ui/connections`**, clicks "Add Jira instance…"
2. **UI form**: fields for Jira URL (`https://yourcompany.atlassian.net`), email, API token (with help link to Atlassian's PAT page), optional default project key, optional connection label ("Work Jira" vs "Personal Jira").
3. **On submit**:
   - Service validates the credentials by hitting `GET <jira_url>/rest/api/3/myself` with Basic Auth (email + token). If fails: form error, no row written.
   - Writes a `service_connections` row: `provider='jira'`, `connection_kind='api_token'`, `connection_label='Work Jira'`, `access_token_enc=Fernet(token)`, `config_json_enc=Fernet({jira_url, email, default_project})`.
4. **A `jira` MCP server** (added when the v2 ADR for Jira lands) reads the connection at tool-invocation time:
   ```python
   conn = await tokens.get_or_decrypt_connection(run_id, "jira", label)
   # conn.access_token = "<PAT>"
   # conn.config = {"jira_url": "...", "email": "...", "default_project": "PROJ"}
   url = f"{conn.config['jira_url']}/rest/api/3/search"
   auth = (conn.config['email'], conn.access_token)
   ```
5. **The flow-coach workflow's `tools.allow`** can be expanded to include `mcp:jira` if the user wants Vacanti-style metrics over Jira issues instead of (or alongside) GitHub PRs.

## 5. Consequences

### Positive

- **The boundary is explicit and small.** Four tiers, one ADR, one schema table for credentials.
- **Adding a new API-token integration doesn't require a redeploy.** The schema already supports it; the UI just needs a form. (Code for the new MCP server is needed; that's expected.)
- **flowmetrics gets `GH_TOKEN` via the cleanest possible path** — reusing the existing GitHub OAuth token via the per-run cache. No new credential to manage.
- **Tool-specific defaults are version-controlled** by living in workflow YAML. Owner can diff/rollback.
- **Per-user isolation is honored** (per ADR-0010); `service_connections.user_id` is enforced by `UserScopedSession`.

### Negative

- **`config_json_enc` is opaque to SQL queries.** You can't `WHERE config_json_enc->>'jira_url' = ...` against it because it's encrypted. Mitigation: queries that need indexed access (e.g. "list all Jira connections pointing at the same URL") are exceedingly rare; if needed, denormalize the specific field to a non-encrypted column.
- **The two-pattern table** (OAuth vs API-token) means some columns are unused for each pattern. ~6 nullable columns total. Tolerable; ALTER TABLE ADD COLUMN with NULL default is cheap.
- **No central "settings" page yet.** Tool defaults are in workflow YAML; user prefs are facts; connections are at `/ui/connections`. A user looking for "where do I change X" has three places to look. v1 doc covers the map; future v2 may want a `/ui/settings` aggregator.

### Operational

- Migration 0001 (Phase 0 task 0.3) includes `connection_kind` and `config_json_enc` columns from day one (nullable). No future migration churn for the v2 integrations.
- `/ui/connections` page in Phase 1 (task 1.7) renders only OAuth providers in v1, but the underlying data model is the same one v2 extends.
- `docs/ops.md` documents the four-tier model so future contributors (or future-me) don't relitigate.

## 6. Alternatives considered

### 6.1 Pure 12-factor (everything in `.env`)

Put per-user credentials in env. `KNO_DYLAN_JIRA_TOKEN`, `KNO_ALICE_JIRA_TOKEN`, etc.

**Rejected** because:
- Doesn't scale past one user.
- Doesn't support "add a new integration" without redeploy.
- The original 12-factor app paper predates per-user multi-integration scenarios; "config" in their sense is server-bootstrap config, which we honor in Tier 1.

### 6.2 Single "settings" key-value table

One big `settings(scope, key, value_enc)` table for everything: bootstrap config + user credentials + workflow defaults + agent prefs.

**Rejected** because:
- Loses type structure. Every value is a JSON blob; queries are awkward; pydantic boundaries are lost.
- Conflates audiences (operator vs user vs agent) at the same table.
- Encryption story is "everything encrypted" — fine for credentials, overkill for "default window in days."

### 6.3 Separate tables for credentials vs integration config

Two tables: `service_credentials(user, provider, token_enc)` and `service_integrations(user, provider, config_json_enc)`. Join them.

**Rejected** because:
- Almost always 1:1 with `service_connections`. Joining for every tool call is a non-trivial cost for no payoff.
- The two-table version is also less natural to teach ("which one do I look at first?").

### 6.4 HashiCorp Vault / 1Password / external secrets manager

Push all credentials to an external secrets manager. Kno fetches at runtime via an SDK.

**Rejected** for v1 because:
- Adds a hosted dependency.
- Doesn't solve the "where does the Jira URL go" question (still need a config store).
- Worth revisiting if Kno ever scales to a deployment with serious operational compliance needs.

### 6.5 Per-MCP-server config files

Each MCP server has its own `data/mcp-config/<server>/<user>.yaml`. Filesystem-as-truth for config too.

**Rejected** because:
- Filesystem for credentials is a worse audit story than encrypted DB (file perms, accidental git commits).
- Loses the existing per-run-decryption + audit-log mechanism that `service_connections` already has via ADR-0005.

## 7. Verification (Phase 0 + Phase 1)

- **Phase 0 task 0.3**: migration 0001 includes `connection_kind` and `config_json_enc` columns. Unit test asserts schema shape.
- **Phase 0 task 0.4**: Google OAuth connection writes `connection_kind='oauth'` and leaves `config_json_enc` NULL. Unit test asserts.
- **Phase 1 task 1.7**: GitHub OAuth connection same pattern.
- **Phase 1 task 1.9**: flowmetrics subprocess invocation passes `GH_TOKEN` env from the per-run cache; integration test asserts the env var is present and the cached token is reused across calls in the same run.
- **Phase 2 docs/ops.md**: documents the four-tier model; documents the v2 extension path for adding a new API-token integration.

## 8. Open questions deferred

- **A `/ui/settings` aggregator** that surfaces all four tiers in one place — useful when the surface grows beyond a few connections + a few workflows. Defer until pain.
- **Per-tool, per-user prefs** (e.g. "Dylan prefers `--since 30d` for flowmetrics but Alice prefers `--since 90d`"). Today this lives in `semantic_facts` if the agent learns it, or in workflow YAML if it's a hard default. A `user_preferences` table would centralize it; defer until there are >5 such prefs.
- **Encryption key rotation** of `config_json_enc` rows (per ADR-0018 §2.3 item 7): `kno rotate-keys` re-wraps both `access_token_enc` AND `config_json_enc`. Documented in `docs/ops.md` at implementation time.
- **Connection-pre-flight check on save** (validates the credential before persisting): worth adding for every new provider. Pattern: `service_connections.providers.<name>.validate(token, config)` raises if the credential is bad.
- **Audit logging** for credential reads (which user's Jira token was decrypted when, for which tool call): already implicit via `audit_log` table per ADR-0005; verify the row schema captures `(user_id, provider, tool, run_id, ts)` and no token value.
