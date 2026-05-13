# Kno Ops Manual — deployment and platform operations

> **Audience.** You, deploying Kno to a server (Fly.io is the v1 target) and operating it over time.
>
> **Scope.** Things that happen **outside the app** — the platform setup, the deploy pipeline, the off-machine storage, the DNS — that the in-app web UI (the setup wizard, `/ui/connections`, etc.) can't do for itself.
>
> **Not in this manual.**
> - **Local setup, first boot, first login, first chat** → `docs/notes/setup/local-quickstart.md`. (Post-Phase-2, the setup wizard at `/setup` is the canonical setup surface; the local-quickstart doc is the manual fallback.)
> - **Backup, restore, wipe, export, key rotation** → `docs/notes/data-management.md`. (CLI commands; the procedures live with the data, not the deploy.)
> - **Spec, plan, ADRs** → `docs/spec.md`, `docs/plan.md`, `docs/adr/`.
>
> **The split rationale.** The web app's setup wizard *is* the canonical local-setup documentation. Duplicating it in a static doc creates drift and gives doc-clarity validation two sources of truth. So `ops.md` is small on purpose — only the truly out-of-app, platform-level concerns.

---

## Contents

1. [Deploying to Fly.io](#1-deploying-to-flyio)
2. [GitHub Actions deploy pipeline](#2-github-actions-deploy-pipeline)
3. [Off-machine backup with object storage (v2)](#3-off-machine-backup-with-object-storage-v2)
4. [Custom domain and TLS](#4-custom-domain-and-tls)
5. [Operational tips — logs, ssh, monitoring](#5-operational-tips--logs-ssh-monitoring)
6. [Platform troubleshooting](#6-platform-troubleshooting)
7. [Update history](#7-update-history)

---

## 1. Deploying to Fly.io

### Prerequisites

- A working local Kno (per `docs/notes/setup/local-quickstart.md`). Don't deploy something you haven't run locally.
- A Fly.io account.
- `flyctl` installed: `brew install flyctl` (or platform equivalent).

### One-time setup

```bash
# 1. Authenticate flyctl
fly auth login                  # opens browser

# 2. Initialize the Fly app from your local kno/ checkout
cd kno
fly launch --no-deploy
```

`fly launch` will prompt for:

- **App name.** Pick something memorable; this becomes `<name>.fly.dev`. E.g. `kno-dylan`.
- **Region.** Closest to you for latency.
- **Postgres?** No.
- **Redis?** No.
- **Deploy now?** Decline. We need to provision a volume and set secrets first.

`fly.toml` is now generated. Commit it.

```bash
# 3. Create the persistent volume for data/
fly volumes create kno_data --size 1 --region <your-region>
```

`fly.toml` already references this mount path (`/data` inside the container). One machine, one volume.

### Set Fly secrets

You **cannot** reuse your local `.env` verbatim — the prod deployment needs its own credentials. Specifically:

- **GitHub OAuth App** must be a separate prod registration (callback URL differs; see `docs/notes/setup/local-quickstart.md` §A.4).
- **`KNO_TOKEN_ENC_KEY`** and **`KNO_SESSION_SECRET`** should be fresh values (not your local ones — local + prod sharing encryption keys is poor hygiene).
- **`KNO_ANTHROPIC_API_KEY`** — recommend a separate key dedicated to prod for cleaner billing/spend caps.
- **`KNO_GOOGLE_CLIENT_ID/SECRET`** — can reuse local (Google supports multiple redirect URIs per client; you already registered both in `docs/notes/setup/local-quickstart.md` §A.3 step 15).

Set them all:

```bash
fly secrets set \
  KNO_ADMIN_EMAIL=you@example.com \
  KNO_TOKEN_ENC_KEY=<fresh Fernet key> \
  KNO_SESSION_SECRET=<fresh urlsafe random> \
  KNO_GOOGLE_CLIENT_ID=<from local, fine to reuse> \
  KNO_GOOGLE_CLIENT_SECRET=<from local, fine to reuse> \
  KNO_GITHUB_CLIENT_ID=<from PROD OAuth App, not local> \
  KNO_GITHUB_CLIENT_SECRET=<from PROD OAuth App, not local> \
  KNO_ANTHROPIC_API_KEY=<fresh prod key>
```

**Ollama notes.**
- Fly's standard machines don't have GPUs and aren't great for Ollama. The prod deploy uses Anthropic only; the Anthropic-outage fallback degrades to "service unavailable" rather than "Ollama fallback."
- If you really want Ollama in prod, a separate Fly machine with `nvidia-flag` or a dedicated GPU host is needed. Beyond v1 scope.
- For now, set Ollama env vars to empty/unset; the server boots without them but the fallback chat model probe will report `chat: not_configured`.

### First deploy

```bash
fly deploy
```

This builds the multi-stage Dockerfile in the repo, pushes the image, and starts the machine.

### Verify

```bash
curl -s https://<your-app>.fly.dev/api/health | jq .
```

Expected:

```json
{
  "ok": true,
  "version": "<sha>",
  "db": "ok",
  "anthropic": "ok",
  "ollama": "not_configured"
}
```

Then open `https://<your-app>.fly.dev/ui/login` in a browser and log in via Google.

### Setup wizard on Fly

Post-Phase-2: when you first deploy a Fly machine with no `.env`-equivalent secrets, the setup mode kicks in. **However**, the wizard's "write `.env`" step doesn't make sense in a container — `.env` would be wiped on next deploy. Two options:

- **Run the wizard locally first** with `KNO_DEPLOY_TARGET=fly` set. The wizard's final step emits a single `fly secrets set ...` shell command containing all the values; copy and run it.
- **Or set all the secrets via `fly secrets set` directly**, as documented above. Skip the wizard for Fly entirely.

Recommended: the first approach. The wizard's live validation is still useful; the output is just shell commands instead of a `.env` write.

---

## 2. GitHub Actions deploy pipeline

The `.github/workflows/deploy.yml` workflow auto-deploys on `main` push after CI passes.

### One-time setup

1. **Get a Fly API token:**
   ```bash
   fly tokens create deploy
   ```
   Copy the token. Treat it like a password.

2. **Add it as a GitHub secret:**
   - https://github.com/dvhthomas/kno/settings/secrets/actions
   - **"New repository secret"**
   - Name: `FLY_API_TOKEN`
   - Value: the token from step 1

3. **Optional: branch protection on `main`:**
   - https://github.com/dvhthomas/kno/settings/branches
   - Require status checks (CI) before merging
   - Require linear history (avoids merge commits cluttering the deploy log)

### How it works

`.github/workflows/ci.yml` runs on every push and PR:
- ruff (lint)
- mypy --strict
- pytest (unit + integration)
- eval suite (against mocked Anthropic in CI)

`.github/workflows/deploy.yml` runs on push to `main` after CI succeeds:
- `flyctl deploy --remote-only` using `FLY_API_TOKEN`
- Posts a comment on the merge commit with deploy result

### Manual deploy from your laptop (skip CI)

```bash
fly deploy
```

Use sparingly — it bypasses CI's lint/type/test gates. The CI-driven path is the default for a reason.

---

## 3. Off-machine backup with object storage (v2)

> **Status.** v2 deliverable. v1 ships with Fly volume snapshots (`fly volumes snapshots list <vol>`) as the off-machine backup story. This section documents the v2 design so future-us has a target.

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

Backups contain `service_connections` rows (encrypted with `KNO_TOKEN_ENC_KEY`). To rotate `KNO_TOKEN_ENC_KEY` you also rotate backup encryption — or you rely on the backup being already-encrypted at the SQLite-column level. v2 design adds a *second* encryption layer at the tarball level via `KNO_BACKUP_ENCRYPTION_KEY` so even a leaked bucket doesn't yield readable backups.

### Daily backup cron (v2)

`scripts/daily_backup.py`:
1. `kno backup` → tarball
2. Encrypt under `KNO_BACKUP_ENCRYPTION_KEY`
3. Upload to S3-compatible bucket
4. Retention: 14 daily + 12 weekly + 6 monthly (configurable)
5. Smoke-test: download the most recent backup, decrypt, run `PRAGMA integrity_check`

Runs as a Fly scheduled machine. Alerts via structured log + (optionally) a webhook to Slack/Discord/email.

### Restore from off-machine (v2)

```bash
uv run kno restore-from-s3 --date 2026-05-13
```

Downloads, decrypts, runs `kno restore`. Documented in `docs/notes/data-management.md` once v2 ships.

### v1 alternative — Fly volume snapshots

For v1, off-machine backup = `fly volumes snapshots list <volume>` + `fly volumes snapshots restore <snapshot-id>`. Adequate but Fly-locked.

```bash
# Snapshots are automatic on Fly (every few days, retained ~5 days)
fly volumes snapshots list kno_data
# To restore: clone the snapshot into a new volume, point the machine at it
```

If you want longer retention or off-Fly storage in v1, the manual workaround:

```bash
# SSH in, kno backup, scp out
fly ssh console
> uv run kno backup --output -
# Pipe to a local file via fly sftp
fly sftp shell
> get /app/kno-backup-<ts>.tar.gz
```

Awkward but works.

---

## 4. Custom domain and TLS

### Skip if you're fine with `<your-app>.fly.dev`

That domain works out of the box with valid TLS. Skip this section.

### If you want `kno.yourdomain.com`

1. **Add the cert in Fly:**
   ```bash
   fly certs add kno.yourdomain.com
   ```

2. Fly prints DNS records you need to add. Two patterns:
   - **CNAME** (simpler): `kno.yourdomain.com → <your-app>.fly.dev`
   - **A + AAAA** (apex / more robust): point at Fly's IPs

3. **Update your DNS** (Cloudflare, Route 53, whatever) with the records Fly gave you.

4. **Wait for propagation** (usually minutes, can be hours):
   ```bash
   fly certs show kno.yourdomain.com
   # Status should go from "awaiting configuration" to "ready"
   ```

5. **Update OAuth callback URLs** at Google + GitHub:
   - Google: add `https://kno.yourdomain.com/api/auth/google/callback` as an authorized redirect URI (Google supports multiple).
   - GitHub: callback URLs are single-value per OAuth App; register a *third* OAuth App for the custom domain if you want both `.fly.dev` and the custom domain to work. Or just retire the `.fly.dev`-callback App once the custom domain works.

### TLS

Fly handles TLS automatically via Let's Encrypt. No cert config in `fly.toml`. Renews automatically.

---

## 5. Operational tips — logs, ssh, monitoring

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

Drops you into a shell inside the container. From there:

```bash
cd /app
uv run kno serve  # already running; this is for ad-hoc commands
sqlite3 /data/kno.db "SELECT count(*) FROM runs;"
```

**Backup from inside the container:**

```bash
fly ssh console
> uv run kno backup --output /tmp/kno-backup.tar.gz
> exit

fly sftp shell
> get /tmp/kno-backup.tar.gz
```

### Cost monitoring (Anthropic spend)

The `model_calls` table is the source of truth. From SSH:

```bash
sqlite3 /data/kno.db \
  "SELECT date(ts) AS day, sum(cost_usd) FROM model_calls GROUP BY day ORDER BY day DESC LIMIT 14;"
```

Or visit `/admin/cost` in the UI (Phase 2 deliverable).

### Honeycomb traces

If `KNO_HONEYCOMB_KEY` is set, every agent run and every model call shows up at `ui.honeycomb.io`. Useful for:

- "Why was that one panel run 3x slower than usual?" — drill into spans.
- "Which workflow has the highest p99 latency?" — query per-workflow.
- "What does a typical Flow Coach run look like end-to-end?" — single-trace view.

For v1's expected load (1 user, a few runs per hour), this is overkill but cheap and educational.

---

## 6. Platform troubleshooting

Issues that happen *outside* the app — the in-app errors are surfaced in the UI itself. This section is for "deploy broke" / "container won't start" / "DNS isn't resolving" scenarios.

### `fly deploy` fails with "no machine available"

Region may be temporarily out of capacity. Try a different region:

```bash
fly machines list
fly scale count 1 --region <different-region>
```

### Container starts but immediately crashes

Tail the logs:

```bash
fly logs --no-tail | tail -100
```

Common causes:

- Missing required env var → boot fails with `ConfigError: KNO_FOO is required`. Set via `fly secrets set`.
- DB migration mismatch → `alembic upgrade head` failed on the volume. SSH in, run by hand to see the error.
- Volume not mounted → log shows `data/ doesn't exist`. Verify `fly.toml` has the mount declaration.

### Custom domain shows "awaiting configuration" forever

DNS hasn't propagated. Try:

```bash
dig kno.yourdomain.com
```

Compare against what Fly told you to add. Common gotchas:
- TTL too high — wait longer
- Proxied through Cloudflare with "Orange Cloud" enabled — disable proxying for the Kno record, OR configure Cloudflare to use Origin Server for Fly
- Wrong record type (A vs CNAME vs ALIAS)

### TLS cert won't issue

```bash
fly certs show kno.yourdomain.com
```

Status will tell you what's missing. Most often: DNS records pointing at a different IP.

### `fly logs` shows no output

Likely the container isn't logging to stderr. Verify `KNO_LOG_LEVEL=INFO` (or DEBUG) is set, and that `structlog` is configured to write to stderr (default).

### Anything else

1. **In-app errors**: check the chat UI's error banner, `/ui/runs/<id>` timeline, or `/api/health`.
2. **Platform-level errors**: `fly logs`, `fly status`, `fly ssh console`.
3. **For the rest**: `docs/spec.md`, `docs/adr/`, or open an issue with the symptom and log excerpt.

---

## 7. Update history

| Date | Change |
|---|---|
| 2026-05-13 | Initial ops manual. Local setup migrated to `docs/notes/setup/local-quickstart.md`; backup/wipe/export/rotate migrated to `docs/notes/data-management.md`. This doc now scoped to platform / deploy / off-machine operations only. |
| 2026-05-13 (earlier) | First version included local setup + per-provider OAuth setup; superseded by the split when it became clear the web setup wizard is the canonical setup surface. |
