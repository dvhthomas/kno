# Kno Ops Manual — deployment milestones

> **Audience.** You, deploying Kno to a server (Fly.io is the v1 target) and operating it over time.
>
> **Structure.** This doc is organized as **deploy milestones**, not topics. Each milestone has an explicit pre-requisite list (build tasks that must be done first; OAuth credentials you need) and an explicit verifiable result. Read top-to-bottom; stop wherever you want — every milestone leaves you with a working deployed thing.
>
> **Not in this manual.**
> - Local setup (running Kno on your laptop) → [`docs/notes/setup/local-quickstart.md`](notes/setup/local-quickstart.md)
> - Backup / restore / wipe / export / key rotation → [`docs/notes/data-management.md`](notes/data-management.md)
> - Spec, plan, ADRs → [`docs/spec.md`](spec.md), [`docs/plan.md`](plan.md), [`docs/adr/`](adr/)
>
> **If you've never built Kno before.** Start at the bottom of [`docs/plan.md`](plan.md) (Pre-flight + Phase 0). You can't deploy zero code; this doc assumes Phase 0 has at least begun.

---

## Contents

0. [Before any deploy: build pre-requisites](#0-before-any-deploy)
1. [Milestone 1 — Hello, Kno: minimum-viable deploy](#1-milestone-1--hello-kno)
2. [Milestone 2 — Add Google sign-in](#2-milestone-2--add-google-sign-in)
3. [Milestone 3 — Add Anthropic + chat](#3-milestone-3--add-anthropic--chat)
4. [Milestone 4 — Add GitHub + Flow Coach + KB-QA (full Kno-Lite)](#4-milestone-4--full-kno-lite)
5. [GitHub Actions CI + auto-deploy](#5-github-actions-ci--auto-deploy)
6. [Off-machine backup with object storage (v2)](#6-off-machine-backup-with-object-storage-v2)
7. [Custom domain and TLS](#7-custom-domain-and-tls)
8. [Operational tips — logs, ssh, monitoring](#8-operational-tips--logs-ssh-monitoring)
9. [Platform troubleshooting](#9-platform-troubleshooting)
10. [Update history](#10-update-history)

---

## 0. Before any deploy

**You can't deploy zero code.** The minimum-viable Kno requires *some* Phase 0 work to exist before any `fly deploy` makes sense.

### Pre-flight (your machine, no code yet)

These don't depend on any Kno code. You can do them while Phase 0 is being built or before.

| Task | Source |
|---|---|
| P0-pre.2: install `uv` (Python 3.12), `ollama`, `flyctl`, `git` | `docs/tasks.md` |
| P0-pre.3: provision a Fly.io account | https://fly.io/ |

Note: **no OAuth credentials, no Anthropic key, no Ollama pulls** are needed yet for Milestone 1. Those come in later milestones.

### Build tasks required for Milestone 1

| Task | Status | What it produces |
|---|---|---|
| `tasks.md` 0.1 — project skeleton | needed | `pyproject.toml`, `Makefile`, `src/kno/__init__.py`, `tests/conftest.py` |
| `tasks.md` 0.2 — config layer | needed | `kno.config.Settings`; **must boot cleanly with no secrets set** (setup-mode style; missing-secrets becomes `{provider}: not_configured` in `/api/health`, not a crash) |
| `tasks.md` 0.10 — web shell + health | needed | `GET /api/health`; `GET /ui/` placeholder |
| `tasks.md` 2.7 — Dockerfile + `fly.toml` (minimal) | pulled forward | A multi-stage Dockerfile + a `fly.toml` with the volume mount |

That's ~4 tasks. ~half a day of focused build work before the first Fly deploy is possible.

> **Phase 0 constraint:** Task 0.2 (config layer) needs to be lenient about missing secrets, **not fail-fast**. The "fail-fast on missing required env vars" pattern only applies once the setup wizard exists (Phase 2). Pre-wizard, the server boots, reports `not_configured`, and shows a placeholder page. This is what makes Milestone 1 possible.

---

## 1. Milestone 1 — Hello, Kno

**Goal.** Deploy an empty Kno scaffold to Fly. No login, no chat, no KB. Just a `/api/health` that responds and a `/ui/` placeholder. Purpose: **validate the deploy pipeline works** before adding anything that depends on it.

### Pre-requisites

- Pre-flight done: `flyctl` installed, Fly account ready.
- Build tasks 0.1, 0.2, 0.10, and minimal 2.7 done (per §0).
- **No OAuth credentials required.** **No Anthropic key required.**

### Steps

```bash
# 1. Authenticate flyctl
fly auth login                  # opens browser

# 2. Initialize the Fly app
cd kno
fly launch --no-deploy
```

`fly launch` prompts:

- **App name** → memorable; this becomes `<name>.fly.dev` (e.g. `kno-dylan`). Remember it.
- **Region** → closest for latency.
- **Postgres?** → No.
- **Redis?** → No.
- **Deploy now?** → No (we still need the volume).

`fly.toml` is generated. Commit it.

```bash
# 3. Create the persistent volume for data/
fly volumes create kno_data --size 1 --region <your-region>
```

```bash
# 4. Deploy
fly deploy
```

### Verify

```bash
curl -s https://<your-app>.fly.dev/api/health | jq .
```

Expected:

```json
{
  "ok": false,
  "version": "<sha>",
  "db": "ok",
  "anthropic": "not_configured",
  "ollama": "not_configured",
  "google_oauth": "not_configured",
  "github_oauth": "not_configured"
}
```

`ok: false` is **expected and correct** at this milestone — Kno is alive but nothing is configured. `db: ok` means the volume mounted and migrations ran. `not_configured` everywhere else means we'll fix those in later milestones.

```bash
# Also check the placeholder page
open https://<your-app>.fly.dev/ui/
```

You should see a placeholder ("Kno is running; setup not yet completed").

**You're done with Milestone 1.** The deploy pipeline works. Continue to Milestone 2 only when build Tasks 0.3/0.4/0.5/0.9 are done (DB tables, Google OAuth, sessions, token vault).

---

## 2. Milestone 2 — Add Google sign-in

**Goal.** `/ui/login` works. You can sign in with Google and reach `/ui/` showing your email.

### Pre-requisites

- Milestone 1 deployed.
- Build tasks 0.3, 0.4, 0.5, 0.9 done (per `docs/tasks.md`): DB migrations, Google OAuth provider, sessions, token vault.
- **A prod Google OAuth client registered** (callback URL = `https://<your-app>.fly.dev/api/auth/google/callback`). See [`docs/notes/setup/local-quickstart.md` §A.3](notes/setup/local-quickstart.md#a3-google-oauth-client) for the click-by-click — Google supports multiple redirect URIs per client, so you can reuse your local-dev client by adding the Fly callback URL to it.

### Steps

```bash
# 1. Generate prod-only secrets (do NOT reuse local values).
KEK=$(uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
SESSION=$(uv run python -c "import secrets; print(secrets.token_urlsafe(32))")

# 2. Set Fly secrets
fly secrets set \
  KNO_ADMIN_EMAIL=you@example.com \
  KNO_TOKEN_ENC_KEY="$KEK" \
  KNO_SESSION_SECRET="$SESSION" \
  KNO_GOOGLE_CLIENT_ID=<from your Google OAuth client> \
  KNO_GOOGLE_CLIENT_SECRET=<from your Google OAuth client>

# 3. Deploy (Fly redeploys automatically when secrets change, but explicit is clearer)
fly deploy
```

### Verify

```bash
curl -s https://<your-app>.fly.dev/api/health | jq .
# google_oauth should now be "ok"
```

Open `https://<your-app>.fly.dev/ui/login` in a browser. Sign in with your Google account (must match `KNO_ADMIN_EMAIL`). You should land on `/ui/` with your email shown.

If "Access blocked" appears: your Google account is not in the OAuth client's Test Users list. See [`docs/notes/setup/local-quickstart.md` §A.3 step 8](notes/setup/local-quickstart.md#a3-google-oauth-client).

**You're done with Milestone 2.** Continue to Milestone 3 when Phase 0 chat tasks (0.6, 0.8, 0.11–0.22) are done.

---

## 3. Milestone 3 — Add Anthropic + chat

**Goal.** You can chat with Kno (the default workflow) signed in. No KB, no Flow Coach — just default chat with persistent memory.

### Pre-requisites

- Milestone 2 deployed.
- Phase 0 chat tasks done: 0.6 (LiteLLM), 0.8 (LangGraph state + checkpointer), 0.11/0.12 (skill + workflow loaders), 0.13–0.16 (memory + chat workflow runtime), 0.17 (reliability checks), 0.18 (default workflow seed), 0.19/0.20 (chat API + UI), 0.21 (feedback), 0.22 (runs view).
- An Anthropic API key (separate from local for clean spend tracking is recommended).

### Steps

```bash
# 1. Set Anthropic key
fly secrets set KNO_ANTHROPIC_API_KEY=sk-ant-api03-...

# 2. Deploy
fly deploy
```

### Verify

```bash
curl -s https://<your-app>.fly.dev/api/health | jq .
# anthropic should now be "ok"
```

Sign in. Visit `/ui/chat`. Pick the `default` workflow. Type "Hey Kno, my name is Dylan. Remember that."

You should see streaming output. Then restart the Fly machine (`fly machine restart <id>`), sign back in, click yesterday's thread, type "Who am I?" — response should say "You're Dylan."

### Ollama on Fly

Skip. Fly's standard machines don't have GPUs and aren't appropriate for Ollama models. The Anthropic-outage fallback degrades to "service unavailable" in prod rather than the Ollama fallback that works locally. (v2 might address this with a separate GPU machine.)

For now: `KNO_OLLAMA_BASE_URL` stays unset on Fly. The `/api/health` will continue to show `ollama: not_configured`; this is fine.

**You're done with Milestone 3.** Continue to Milestone 4 when Phase 1 tasks are done (GitHub OAuth + flowmetrics MCP + KB ingestion + librarian/vacanti workflows).

---

## 4. Milestone 4 — Full Kno-Lite

**Goal.** Full Kno-Lite: signed-in chat + Flow Coach + KB-QA + connections page.

### Pre-requisites

- Milestone 3 deployed.
- Phase 1 tasks done: 1.1–1.16 (KB ingestion + retrieval, github + flowmetrics MCP servers, seed workflows for librarian + vacanti, approval gate, eval suite, prompt-injection battery).
- **A prod GitHub OAuth App registered** (callback URL = `https://<your-app>.fly.dev/api/auth/github/callback`). GitHub OAuth Apps allow only one callback URL — this **must** be a separate registration from your local-dev App. See [`docs/notes/setup/local-quickstart.md` §A.4](notes/setup/local-quickstart.md#a4-github-oauth-apps).

### Steps

```bash
# 1. Set GitHub OAuth secrets (from the PROD OAuth App, not local)
fly secrets set \
  KNO_GITHUB_CLIENT_ID=<prod app client ID> \
  KNO_GITHUB_CLIENT_SECRET=<prod app client secret>

# 2. Deploy
fly deploy
```

### Verify

```bash
curl -s https://<your-app>.fly.dev/api/health | jq .
# All providers should now be "ok" (except ollama, which stays not_configured on Fly)
```

Sign in. Visit `/ui/connections`. Click "Connect with GitHub" → authorize → return to `/ui/connections` showing GitHub connected.

Visit `/ui/kb`. Click "Sync" on a Hugo source repo (e.g. `dvhthomas/bitsby-me`). Wait for chunks to index.

Visit `/ui/chat`. Pick `kb-qa` → ask a question about a post → get a cited answer. Pick `flow-coach` → ask "how is dvhthomas/kno doing this month?" → get a Vacanti-style summary.

**You're done with Milestone 4.** This is full Kno-Lite deployed.

---

## 5. GitHub Actions CI + auto-deploy

Optional but recommended. Replaces manual `fly deploy` with push-to-main → deploy.

### Pre-requisites

- Any of Milestones 1–4 deployed.
- `.github/workflows/ci.yml` and `.github/workflows/deploy.yml` exist in the repo (Phase 2 Task 2.8).

### One-time setup

1. **Get a Fly API token:**
   ```bash
   fly tokens create deploy
   ```
   Copy the token. Treat it like a password.

2. **Add it as a GitHub secret:**
   - https://github.com/dvhthomas/kno/settings/secrets/actions
   - "New repository secret" → Name: `FLY_API_TOKEN` → Value: the token from step 1.

3. **Optional: branch protection on `main`:**
   - https://github.com/dvhthomas/kno/settings/branches
   - Require status checks (CI) before merging.
   - Require linear history.

### How it works

`.github/workflows/ci.yml` runs on every push and PR:
- ruff (lint)
- mypy --strict
- pytest (unit + integration)
- eval suite (mocked Anthropic in CI)

`.github/workflows/deploy.yml` runs on push to `main` after CI succeeds:
- `flyctl deploy --remote-only` using `FLY_API_TOKEN`
- Posts a comment on the merge commit with deploy result.

### Manual deploy still works

```bash
fly deploy
```

Bypasses CI's quality gates. Use sparingly.

---

## 6. Off-machine backup with object storage (v2)

> **Status.** v2 deliverable. v1 ships with Fly volume snapshots as the off-machine backup story. This section documents the v2 design.

### Why off-machine backup matters

The Fly volume has a single point of failure. Volume snapshots help, but they live on Fly. A real off-machine backup means a copy in a different cloud / location.

### Target architecture (v2)

```
[Fly machine]  ──daily cron──►  [S3-compatible bucket]
    │                                    │
  data/                            kno-backups/
    └─ kno.db                         ├─ 2026-05-13.tar.gz.enc
    └─ workflows/                     ├─ 2026-05-14.tar.gz.enc
    └─ skills/                        └─ ...
    └─ agents/
```

### Provider options

| Provider | Notes |
|---|---|
| **Cloudflare R2** | S3-compatible API. No egress fees. ~$0.015/GB/month. Recommended for v2. |
| **Backblaze B2** | S3-compatible. Even cheaper than R2 for storage. Some egress fees. |
| **AWS S3** | Standard. More expensive than R2/B2 for this use case. |
| **Tigris** | Built into Fly Platform — easy provisioning. |

Recommendation when v2 ships: **Cloudflare R2** (zero egress = restore-time is free) or **Tigris** (zero-config integration with Fly).

### Required env vars (v2)

```
KNO_BACKUP_S3_ENDPOINT=https://<account>.r2.cloudflarestorage.com
KNO_BACKUP_S3_BUCKET=kno-backups
KNO_BACKUP_S3_ACCESS_KEY=<from provider>
KNO_BACKUP_S3_SECRET_KEY=<from provider>
KNO_BACKUP_S3_REGION=auto    # R2 quirk
KNO_BACKUP_ENCRYPTION_KEY=<separate Fernet key for backup-at-rest>
```

Set via `fly secrets set ...` for prod.

### Encryption-at-rest for backups

Backups contain `service_connections` rows (encrypted with `KNO_TOKEN_ENC_KEY`). v2 design adds a *second* encryption layer at the tarball level via `KNO_BACKUP_ENCRYPTION_KEY` so even a leaked bucket doesn't yield readable backups.

### Daily backup cron (v2)

`scripts/daily_backup.py`:
1. `kno backup` → tarball
2. Encrypt under `KNO_BACKUP_ENCRYPTION_KEY`
3. Upload to S3-compatible bucket
4. Retention: 14 daily + 12 weekly + 6 monthly (configurable)
5. Smoke-test: download the most recent backup, decrypt, run `PRAGMA integrity_check`

Runs as a Fly scheduled machine.

### Restore from off-machine (v2)

```bash
uv run kno restore-from-s3 --date 2026-05-13
```

Documented in `docs/notes/data-management.md` once v2 ships.

### v1 alternative — Fly volume snapshots

For v1, off-machine backup = `fly volumes snapshots list <volume>` + restore by cloning the snapshot. Adequate but Fly-locked.

```bash
fly volumes snapshots list kno_data
# To restore: clone the snapshot into a new volume, point the machine at it.
```

For longer retention or off-Fly storage in v1: `fly ssh console` → `uv run kno backup --output -` → pipe to a local file via `fly sftp shell`. Awkward but works.

---

## 7. Custom domain and TLS

### Skip if you're fine with `<your-app>.fly.dev`

That domain works out of the box with valid TLS. Skip this section.

### If you want `kno.yourdomain.com`

1. **Add the cert in Fly:**
   ```bash
   fly certs add kno.yourdomain.com
   ```

2. Fly prints DNS records to add. Two patterns:
   - **CNAME** (simpler): `kno.yourdomain.com → <your-app>.fly.dev`
   - **A + AAAA** (apex / more robust): point at Fly's IPs

3. **Update your DNS** with the records Fly gave you.

4. **Wait for propagation** (usually minutes, can be hours):
   ```bash
   fly certs show kno.yourdomain.com
   # Status: "awaiting configuration" → "ready"
   ```

5. **Update OAuth callback URLs** at Google + GitHub:
   - Google: add `https://kno.yourdomain.com/api/auth/google/callback` (Google supports multiple).
   - GitHub: register a *new* OAuth App for the custom domain (GitHub allows only one callback URL per App).

### TLS

Fly handles TLS via Let's Encrypt automatically. No cert config in `fly.toml`. Renews automatically.

---

## 8. Operational tips — logs, ssh, monitoring

### Tail logs

```bash
fly logs                          # live tail from all machines
fly logs --no-tail                # last N lines, exit
fly logs --instance <machine-id>  # specific machine if you have >1
```

### SSH into a Fly machine

```bash
fly ssh console
```

From inside:

```bash
sqlite3 /data/kno.db "SELECT count(*) FROM runs;"
```

### Backup from inside the container

```bash
fly ssh console
> uv run kno backup --output /tmp/kno-backup.tar.gz
> exit

fly sftp shell
> get /tmp/kno-backup.tar.gz
```

See [`docs/notes/data-management.md`](notes/data-management.md) for the full backup/restore/wipe/export/rotate procedures.

### Cost monitoring (Anthropic spend)

The `model_calls` table is the source of truth. From SSH:

```bash
sqlite3 /data/kno.db \
  "SELECT date(ts) AS day, sum(cost_usd) FROM model_calls GROUP BY day ORDER BY day DESC LIMIT 14;"
```

Or visit `/admin/cost` (Phase 2 deliverable).

### Honeycomb traces

If `KNO_HONEYCOMB_KEY` is set, every agent run and every model call shows up at `ui.honeycomb.io`. Optional, low cost, useful for "why was that run weird?" debugging.

---

## 9. Platform troubleshooting

In-app errors are surfaced by the UI itself. This section is for *outside-the-app* failures.

### `fly deploy` fails with "no machine available"

Region temporarily out of capacity. Try another:

```bash
fly machines list
fly scale count 1 --region <different-region>
```

### Container boots but `/api/health` returns 5xx

Tail the logs:

```bash
fly logs --no-tail | tail -100
```

Common causes:

- DB migration mismatch → `alembic upgrade head` failed on the volume. SSH in and run by hand to see the error.
- Volume not mounted → log shows `data/ doesn't exist`. Verify `fly.toml` has the mount declaration.
- Unrecoverable config error → log shows `ConfigError: KNO_FOO is invalid`. Fix via `fly secrets set`.

(Missing optional secrets should not cause a crash; if they do, the config layer is failing too aggressively for Milestone 1 to work — see §0 note.)

### Custom domain stuck on "awaiting configuration"

DNS hasn't propagated. Check:

```bash
dig kno.yourdomain.com
```

Common gotchas:
- TTL too high — wait longer.
- Cloudflare "Orange Cloud" proxying enabled — disable it for the Kno record.
- Wrong record type (A vs CNAME vs ALIAS).

### TLS cert won't issue

```bash
fly certs show kno.yourdomain.com
```

Status tells you what's missing. Most often: DNS records point at the wrong IP.

### `fly logs` shows nothing

Container isn't logging to stderr. Verify `KNO_LOG_LEVEL=INFO` and that `structlog` is configured to write to stderr (the default).

### Anything else

1. In-app errors: `/api/health`, `/ui/runs/<id>` timeline, chat error banner.
2. Platform errors: `fly logs`, `fly status`, `fly ssh console`.
3. Beyond that: `docs/spec.md`, `docs/adr/`, or open an issue with symptom + log excerpt.

---

## 10. Update history

| Date | Change |
|---|---|
| 2026-05-13 | **Restructured around deploy milestones** (Hello-Kno → +Google → +Anthropic → +full Kno-Lite). Each milestone has explicit build pre-requisites + verifiable result. Reader can stop at any milestone with something working. Adds a §0 explaining the build pre-reqs before any deploy is possible. Makes explicit that the config layer must be lenient about missing optional secrets (boots with `not_configured` rather than crashing). |
| 2026-05-13 (earlier) | Split from the original ops.md into ops.md (platform/deploy) + `docs/notes/setup/local-quickstart.md` (local setup) + `docs/notes/data-management.md` (backup/wipe/export/rotate). |
| 2026-05-13 (initial) | First version included local setup + per-provider OAuth setup; superseded by the split when it became clear the web setup wizard is the canonical setup surface. |
