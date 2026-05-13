# Kno-Lite Ops Manual

> **Audience.** Someone with a Mac or Linux laptop and a working brain, who has never set up Kno before. Either you, future-you, or someone you've invited.
>
> **Goal.** From a fresh clone of `dvhthomas/kno`, get Kno running locally in under 60 minutes — first chat turn streaming, your name remembered, costs visible in the ledger.
>
> **The doc-clarity contract.** If you follow this manual top-to-bottom *without consulting other docs* and you hit a dead end, that's a manual bug. Open an issue with the section number and what went wrong. The whole point of v1 is that this works.

---

## Contents

1. [Prerequisites](#1-prerequisites)
2. [Get the code](#2-get-the-code)
3. **[Provider setup](#3-provider-setup)** — env vars from each provider
   - [3.1 Anthropic API key](#31-anthropic-api-key)
   - [3.2 Ollama (local)](#32-ollama-local)
   - [3.3 Google OAuth client](#33-google-oauth-client)
   - [3.4 GitHub OAuth Apps](#34-github-oauth-apps)
   - [3.5 Locally-generated secrets](#35-locally-generated-secrets)
   - [3.6 Honeycomb (optional)](#36-honeycomb-optional)
4. [Writing your `.env`](#4-writing-your-env)
5. [First boot](#5-first-boot)
6. [First login + GitHub connection](#6-first-login--github-connection)
7. [First chat turn](#7-first-chat-turn)
8. [Backup, restore, wipe](#8-backup-restore-wipe)
9. [Key rotation](#9-key-rotation)
10. [Deploying to Fly.io](#10-deploying-to-flyio)
11. [Adding workflows and skills](#11-adding-workflows-and-skills)
12. [Troubleshooting](#12-troubleshooting)
13. [Update history](#13-update-history)

---

## 1. Prerequisites

You need these tools on your machine. The commands assume macOS with Homebrew or a recent Linux with a package manager.

| Tool | Purpose | macOS install | Verify |
|---|---|---|---|
| **Python 3.12** (via uv) | Kno is Python | `brew install uv` then `uv python install 3.12` | `uv python list` shows 3.12.x |
| **uv** | dep manager + script runner | (covered above) | `uv --version` |
| **Ollama** | embeddings + LLM fallback | `brew install ollama` | `ollama --version` |
| **git** | source control | preinstalled (or `brew install git`) | `git --version` |
| **gh** (GitHub CLI) | repo access for KB ingestion (flowmetrics uses it indirectly via env vars; you don't need `gh auth login` for Kno itself, but it's handy for `gh repo clone`) | `brew install gh` | `gh --version` |
| **A text editor** | editing `.env`, workflows, skills | your preference | n/a |
| **A browser** | the Kno UI lives here | your preference | n/a |

**Linux note:** apt/dnf/pacman equivalents exist for all of the above. uv has a one-line installer at https://github.com/astral-sh/uv.

**Verify all at once:**

```bash
uv --version && ollama --version && git --version && gh --version
```

If any of those say "command not found," install it before moving on. The rest of this manual assumes they all work.

---

## 2. Get the code

```bash
git clone https://github.com/dvhthomas/kno.git
cd kno
```

If you're forking, replace the URL with your fork. The rest of this manual assumes `cwd = kno/`.

**Verify:**
```bash
ls docs/
# spec.md  plan.md  tasks.md  ops.md  adr/  notes/
```

---

## 3. Provider setup

> **The fast path: just run `uv run kno serve` and let the web wizard guide you.** The server boots into **setup mode** when `.env` is missing or incomplete, serves a wizard at `http://localhost:8000/setup`, and walks every step below with **live validation** (paste your Anthropic key → server tests it in real time → green check or precise error). Same for Ollama, Google OAuth, GitHub OAuth. Generates the Fernet KEK and session secret with one click. Writes `.env` on submit. ~15 minutes.
>
> **Read this section if** the wizard fails on a step and you need the underlying detail, OR you're doing a Fly deployment (the wizard has a Fly mode that emits `fly secrets set` commands for you, but understanding the provider-side setup helps when troubleshooting), OR you prefer doing it by hand.
>
> After setup is done — by wizard or by hand — signing in with another account inside Kno is a single button click in `/ui/connections` (§6). No developer-console trips, no env-var edits, no Kno restart. The recurring user experience lives in §7 and beyond.

This section is the reference detail behind what the wizard does. The order goes from **simplest** (Anthropic — one click) to **most involved** (GitHub OAuth Apps — you may need two). If you're using the wizard, it walks these in the same order.

By the end of §3 you'll have collected **8–10 values**. The wizard collects them into `.env` directly; if you're doing it by hand, paste each value into a *scratch buffer* and assemble `.env` in §4.

### 3.1 Anthropic API key

**Purpose.** Kno's chat/synth/router model calls go through Anthropic via LiteLLM. Per ADR-0001.

**Time:** ~3 minutes.

**You will end up with:** one env var, `KNO_ANTHROPIC_API_KEY`.

**Steps:**

1. Go to https://console.anthropic.com/.
2. Sign in. If you're on the Max plan, that's the right account — Kno reuses your org's billing.
3. Left nav → **"API keys"** (or top-right gear → API keys).
4. Click **"Create Key"**.
5. Name it `kno-dev` (or `kno-prod` later; one per environment is cleanest).
6. Copy the key starting with `sk-ant-`. **You can't see it again** — save it to your scratch buffer now.
7. Optional but recommended: under **"Workspaces"** or **"Spend limits"**, set a workspace-level monthly cap (e.g. $30) on this key as a hard backstop beyond Kno's own per-session caps.

**Paste into scratch buffer:**
```
KNO_ANTHROPIC_API_KEY=sk-ant-api03-XXXXXXXXXXXX...
```

**Verify the key works:**
```bash
curl -s https://api.anthropic.com/v1/messages \
  -H "x-api-key: sk-ant-api03-..." \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-haiku-4-5","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
```
Expected: a JSON response containing `"content":` with a model reply. If you see `"error"`, the key is wrong or revoked.

**Common pitfalls:**
- Copying the key with a trailing newline or space. Trim it.
- Putting the key in a public repo or a chat. Treat it like a password.

---

### 3.2 Ollama (local)

**Purpose.** Two roles. (a) Embeddings for the KB via `nomic-embed-text` — free, fast, runs on your machine. (b) Chat fallback if Anthropic is unreachable, via `llama3.1:8b` (or `:70b` if you have the RAM).

**Time:** ~5 minutes wall (plus ~5–15 minutes of model download depending on bandwidth).

**You will end up with:** three env vars — `KNO_OLLAMA_BASE_URL`, `KNO_OLLAMA_EMBED_MODEL`, `KNO_OLLAMA_FALLBACK_CHAT_MODEL`. None of them are secrets; defaults work for most people.

**Steps:**

1. Start the Ollama service.
   - macOS: `brew services start ollama` (runs as a launchd service; survives logout).
   - Or run interactively in a terminal tab: `ollama serve`.
2. Pull the embedding model:
   ```bash
   ollama pull nomic-embed-text
   ```
   Downloads ~700 MB. Watch the progress bar.
3. Pull a chat fallback model:
   ```bash
   ollama pull llama3.1:8b
   ```
   Downloads ~5 GB.
   - If you have ≥64 GB RAM and patience: `ollama pull llama3.1:70b` (~40 GB; substantially better quality but slower). Kno-Lite v1 doesn't care which you pick — it uses whichever you set in `.env`.
4. Verify both models are loaded:
   ```bash
   ollama list
   ```
   Expected: a table listing `nomic-embed-text` and `llama3.1:8b` (or whichever you pulled).
5. Smoke-test embeddings end-to-end:
   ```bash
   curl -s http://localhost:11434/api/embeddings \
     -d '{"model":"nomic-embed-text","prompt":"hello"}' | head -c 200
   ```
   Expected: a JSON response containing `"embedding":[<lots of floats>]`. If you see `connection refused`, Ollama isn't running.

**Paste into scratch buffer:**
```
KNO_OLLAMA_BASE_URL=http://localhost:11434
KNO_OLLAMA_EMBED_MODEL=nomic-embed-text
KNO_OLLAMA_FALLBACK_CHAT_MODEL=llama3.1:8b
```

**Common pitfalls:**
- Forgetting to start Ollama (`brew services start ollama` or `ollama serve`). The Anthropic-outage drill in Phase 2 verifies this is actually working — if it's not, the verification will fail loudly.
- Mac firewall blocking `localhost:11434`. Allow it.
- Trying to run a 70b model on a machine with 16 GB RAM. It'll swap, then crawl. Use 8b unless you have 64 GB+.

---

### 3.3 Google OAuth client

**Purpose.** Identity. Kno uses Google to identify you when you log in to `/ui/`. v1 is single-user but the OAuth flow is the same as multi-user — your `KNO_ADMIN_EMAIL` must match the Google account you log in with.

**Time:** ~10 minutes (mostly because Google Cloud Console has multiple confirmation screens).

**You will end up with:** two env vars — `KNO_GOOGLE_CLIENT_ID` and `KNO_GOOGLE_CLIENT_SECRET`.

**Steps:**

1. Go to https://console.cloud.google.com/.
2. Top-left dropdown next to "Google Cloud" → **"New Project"**. Name it `kno-dev` (or reuse an existing project — Google's OAuth client is per-project).
3. Wait for the project to be created; switch to it via the top-left dropdown.
4. Left nav → **"APIs & Services"** → **"OAuth consent screen"**.
5. **User type:** pick **"External"**. Click **"Create"**.
6. **App information:**
   - App name: `Kno` (or `Kno-dev`).
   - User support email: your email.
   - Developer contact email: your email.
   - Leave logo, app domain, etc. blank for now.
   - Click **"Save and continue"**.
7. **Scopes:** click **"Save and continue"** without adding any. (Kno requests scopes at OAuth runtime via code in `src/kno/auth/providers/google.py`, not via the consent screen.)
8. **Test users:** click **"+ Add users"** and add the Gmail address you want to log in as. **Required** while the app is in "Testing" status. Click **"Save and continue"**.
9. **Summary:** click **"Back to dashboard"**.
10. Left nav → **"APIs & Services"** → **"Credentials"**.
11. **"+ Create Credentials"** → **"OAuth client ID"**.
12. **Application type:** select **"Web application"**. **Not "Desktop app"** — that uses a different OAuth flow Kno doesn't support.
13. **Name:** `Kno (local dev)` — for your own reference.
14. **Authorized JavaScript origins:** leave empty.
15. **Authorized redirect URIs:**
    - Click **"+ Add URI"** and paste: `http://localhost:8000/api/auth/google/callback`
    - If you're also planning to deploy to Fly: click **"+ Add URI"** again and paste `https://<your-fly-app-name>.fly.dev/api/auth/google/callback`. (Pick your Fly app name now; you can change it later by editing this OAuth client.)
    - Google allows multiple redirect URIs per client — both can live in one client.
16. Click **"Create"**.
17. A modal appears with **"Your Client ID"** and **"Your Client Secret"**. Copy both. You can get them back later from this page; copy them now anyway.

**Paste into scratch buffer:**
```
KNO_GOOGLE_CLIENT_ID=123456789012-abcdefghij...apps.googleusercontent.com
KNO_GOOGLE_CLIENT_SECRET=GOCSPX-XXXXXXXXXXXX
```

**Common pitfalls:**
- Picking "Desktop app" instead of "Web application" → you'll see `redirect_uri_mismatch` at login time. Edit the client, switch type — actually, you can't; you have to create a new one. So get this right the first time.
- Forgetting to add your Gmail to "Test users" → you'll see "Access blocked: This app's request is invalid" on login. Add yourself.
- The redirect URI has a typo (e.g. `/auth/callback` instead of `/api/auth/google/callback`) → `redirect_uri_mismatch`. Match the URL Kno actually uses, exactly.
- You created the OAuth client in the wrong project → the client ID won't show up in the project Kno thinks it's using. Verify the project name in the top bar matches.

**Verification (after `.env` is populated and Kno is running — coming in §5):**
- Open `http://localhost:8000/ui/login` in your browser.
- Click **"Sign in with Google"**.
- Pick the test-user Gmail you added in step 8.
- Should redirect to `http://localhost:8000/ui/` showing your email.

If the redirect goes nowhere (browser stays on Google), check the Authorized Redirect URI in step 15 against what Kno actually called (server logs will show).

**→ This is a one-time deployer task.** Once Kno is running, adding another Google account (e.g. your work account in addition to personal) is a single button click in `/ui/connections` — no return to Google Cloud Console.

---

### 3.4 GitHub OAuth Apps

**Purpose.** Two MCP servers need GitHub-authenticated access: `github` (read repos for Flow Coach + KB ingestion) and `flowmetrics` (reads via `gh` CLI inheriting `GH_TOKEN` — see ADR-0019 §3).

**Time:** ~7 minutes per OAuth App, and you may need **two** (one for local dev, one for production). See the wrinkle below.

**You will end up with:** two env vars — `KNO_GITHUB_CLIENT_ID` and `KNO_GITHUB_CLIENT_SECRET`. (Or four if you set up dev + prod.)

**The GitHub wrinkle.** Unlike Google, a GitHub OAuth App allows **exactly one callback URL**. If you want to run Kno both locally and on Fly, the cleanest answer is to register **two separate OAuth Apps** at GitHub:

- **App #1:** `Kno (local dev)` with callback `http://localhost:8000/api/auth/github/callback`. Use this app's client ID/secret in your local `.env`.
- **App #2:** `Kno (prod)` with callback `https://<your-fly-app>.fly.dev/api/auth/github/callback`. Use this app's client ID/secret in Fly secrets (per §10).

If you're only running locally for now, do just **App #1** and skip the prod registration until you deploy.

**Alternative for the brave:** use the newer "GitHub App" primitive (not "OAuth App"), which supports multiple callback URLs and finer-grained permissions. **Don't do this** for v1 — it's heavier than we need and the auth flow is different. OAuth App is the right primitive for Kno-Lite.

**Steps (for one OAuth App):**

1. Go to https://github.com/settings/developers.
2. Left nav → **"OAuth Apps"**.
3. Click **"New OAuth App"** (top-right).
4. **Application name:** `Kno (local dev)` for the local one, or `Kno (prod)` for the prod one.
5. **Homepage URL:** `http://localhost:8000` for the local one, or `https://<your-fly-app>.fly.dev` for the prod one. (Doesn't have to resolve right now; just be reachable when someone clicks the link from GitHub's app-management page.)
6. **Application description:** anything; "Personal Kno deployment" is fine.
7. **Authorization callback URL:**
   - Local: `http://localhost:8000/api/auth/github/callback`
   - Prod: `https://<your-fly-app>.fly.dev/api/auth/github/callback`
   - **This is the most error-prone field.** Match Kno's actual callback path: it's `/api/auth/github/callback`, not `/auth/callback`, not `/api/github/callback`.
8. **Enable Device Flow:** leave unchecked.
9. Click **"Register application"**.
10. On the resulting page:
    - **Client ID:** visible at the top. Copy it.
    - **Client secrets:** scroll down. Click **"Generate a new client secret"**. The secret appears once — copy it immediately.

**Paste into scratch buffer:**
```
# Local-dev OAuth App
KNO_GITHUB_CLIENT_ID=Iv1.XXXXXXXXXXXX
KNO_GITHUB_CLIENT_SECRET=XXXXXXXXXXXXXXXXXXXXXXXX
```

(If you registered a prod App too, save its client ID/secret separately for §10.)

**Common pitfalls:**
- Wrong callback URL (most common). Check the exact path in §6 below.
- Using a single OAuth App for local + prod → second deployment fails with `redirect_uri_mismatch`. Register two.
- Confusing "OAuth App" with "GitHub App" in the GitHub UI — the navigation is right next to each other. You want **OAuth Apps**.
- Lost the client secret → you can regenerate, but everywhere it's used (your `.env`, Fly secrets) has to be updated.

**Verification (after Kno is running, §6 below):**
- Open `http://localhost:8000/ui/connections`.
- Click **"Connect with GitHub"**.
- GitHub asks you to authorize Kno (with the `repo` scope, per `src/kno/auth/providers/github.py`).
- Approve → redirect back to `/ui/connections` showing GitHub as connected. The connection label defaults to your GitHub login (e.g. `dvhthomas`); rename inline if you want.

**→ This is a one-time deployer task.** Once Kno is running, adding another GitHub account (e.g. your work-org access in addition to personal) is a single button click in `/ui/connections` — no return to GitHub Developer Settings.

---

### 3.5 Locally-generated secrets

These never touch a provider's website. They're random values you generate on your own machine.

**You will end up with:** two env vars — `KNO_TOKEN_ENC_KEY` (the Fernet KEK that encrypts OAuth tokens at rest per ADR-0019) and `KNO_SESSION_SECRET` (HMAC for signed session cookies).

**Steps:**

1. Generate the Fernet KEK:
   ```bash
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   You'll see a value like `aBcD1234...=`. Copy it.

2. Generate the session secret:
   ```bash
   uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   You'll see a value like `K7n0L1t3...`. Copy it.

**Paste into scratch buffer:**
```
KNO_TOKEN_ENC_KEY=<the Fernet key from step 1>
KNO_SESSION_SECRET=<the random string from step 2>
```

**Common pitfalls:**
- Reusing the same value for both — they have different purposes and different formats. Generate each freshly.
- Generating new values without rotating existing data — if you've already run Kno once and have encrypted tokens in `service_connections`, generating a new `KNO_TOKEN_ENC_KEY` will make those tokens unreadable. Run `kno rotate-keys` (§9) to re-encrypt before changing.
- Committing these to git. **Never.** The `.gitignore` excludes `.env`; verify you haven't `git add .env` by accident.

**Note on `uv run` here:** these commands rely on `cryptography` being installed in the project venv. If `uv sync` hasn't been run yet (§5 hasn't happened), the commands fail. Order: generate secrets *after* you've run `uv sync` once.

---

### 3.6 Honeycomb (optional)

**Purpose.** OpenTelemetry traces for every agent run. Useful for debugging cost or latency anomalies. **Skip this entirely for first-time setup** — Kno runs fine without it.

**Time:** ~3 minutes if you want it.

**You will end up with (optional):** `KNO_HONEYCOMB_KEY` and `KNO_HONEYCOMB_DATASET`.

**Steps:** Go to https://ui.honeycomb.io/, sign up (free tier exists), get an API key from your account settings, pick a dataset name (e.g. `kno-dev`). Paste into your scratch buffer.

If unset, Kno logs structured events to stderr and the tracing exporter no-ops — no errors.

---

## 4. Writing your `.env`

You now have a scratch buffer with **8–10 collected values**. Time to assemble the real `.env`.

```bash
cp .env.example .env
$EDITOR .env
```

Walk through `.env.example` top to bottom. Each section has comments explaining what it's for; here's a checklist that maps to the scratch buffer values:

| Section in `.env.example` | What to fill in | Source |
|---|---|---|
| **Owner & encryption** | `KNO_ADMIN_EMAIL` | The Gmail you used in §3.3 step 8 |
|  | `KNO_TOKEN_ENC_KEY` | §3.5 step 1 |
|  | `KNO_SESSION_SECRET` | §3.5 step 2 |
| **Google OAuth** | `KNO_GOOGLE_CLIENT_ID` | §3.3 |
|  | `KNO_GOOGLE_CLIENT_SECRET` | §3.3 |
| **GitHub OAuth** | `KNO_GITHUB_CLIENT_ID` | §3.4 (local app) |
|  | `KNO_GITHUB_CLIENT_SECRET` | §3.4 (local app) |
| **Anthropic** | `KNO_ANTHROPIC_API_KEY` | §3.1 |
| **Ollama** | (defaults are fine if you used `http://localhost:11434` + `nomic-embed-text` + `llama3.1:8b`) | §3.2 — only change if you used different values |
| **Database** | (default is fine: `sqlite+aiosqlite:///data/kno.db`) | — |
| **Server** | (defaults: `0.0.0.0` + `8000`) | — |
| **Observability** | `KNO_HONEYCOMB_KEY` if you set it up | §3.6 (or leave empty) |
| **Dev / test flags** | (leave all defaults) | — |

**Final sanity check (before first boot):**

```bash
grep -E '^KNO_[A-Z_]+=$' .env
```

Expected: this command returns **nothing**. If any line is empty (`KNO_FOO=`), you missed it.

```bash
grep -E '^[A-Z_]+=$' .env
```

This is broader; any empty var is bad except commented optional ones. The Honeycomb keys are allowed to be empty.

```bash
grep -c '^[A-Z]' .env
```

Counts non-comment lines. Expected: 14–16 (depending on whether you set Honeycomb).

**Common pitfalls:**
- **Quoting.** Don't wrap values in quotes unless they contain spaces (none of Kno's values should). `KNO_ANTHROPIC_API_KEY="sk-ant-..."` works but `KNO_ANTHROPIC_API_KEY=sk-ant-...` is more conventional.
- **Trailing whitespace.** Some editors add a space. The Fernet KEK is sensitive to this.
- **Wrong account on `KNO_ADMIN_EMAIL`.** Must match the Google account you log in with, exactly, case-sensitive.

---

## 5. First boot

**If you used the web setup wizard (§3 fast path)**, `.env` is already written and Kno is already running normally. Skip to §6.

**If you did `.env` by hand**:

```bash
# 1. Install deps + create venv
uv sync

# 2. Create the data directory if it doesn't exist
mkdir -p data

# 3. Run database migrations
uv run alembic upgrade head

# 4. Start Kno
uv run kno serve
```

**If you're starting fresh and haven't created `.env` yet**, just do steps 1, 2, and 4 — the server will boot into setup mode and walk you through the wizard:

```bash
uv sync
mkdir -p data
uv run kno serve
# Boot output will print: "setup mode active; visit http://localhost:8000/setup"
# Plus a setup-token to paste into the first form.
```

Open `http://localhost:8000/setup` in your browser. The wizard handles `.env` write + migration + reload automatically.

**Expected output** at step 4 (rough; actual lines will vary):
```
[info] starting kno-server version=<sha> commit=<sha>
[info] db_integrity_check ok=true
[info] anthropic_probe ok=true model=claude-haiku-4-5
[info] ollama_probe ok=true embed_model=nomic-embed-text chat_model=llama3.1:8b
[info] uvicorn running on http://0.0.0.0:8000
```

**If any of the four probes fail at boot:**
- `anthropic_probe ok=false` → your `KNO_ANTHROPIC_API_KEY` is wrong or revoked. Re-verify with the curl test in §3.1.
- `ollama_probe ok=false embed=false` → Ollama isn't running or the embed model isn't pulled. Run `ollama list` in another terminal; if `nomic-embed-text` is missing, `ollama pull nomic-embed-text`.
- `ollama_probe ok=false chat=false` → fallback chat model not pulled. `ollama pull llama3.1:8b`.
- `db_integrity_check ok=false` → `data/kno.db` is corrupted (rare on first boot — means something went wrong during migration). Delete it (`rm data/kno.db`) and rerun `uv run alembic upgrade head`.

**Health check:**
```bash
curl -s http://localhost:8000/api/health | jq .
```

Expected:
```json
{
  "ok": true,
  "version": "<sha>",
  "db": "ok",
  "anthropic": "ok",
  "ollama": "ok"
}
```

If `ok: false`, the JSON tells you which subsystem failed. Fix and restart.

---

## 6. First login + GitHub connection

1. Open `http://localhost:8000/ui/login` in your browser.
2. Click **"Sign in with Google"**.
3. Google's consent screen appears. Pick your `KNO_ADMIN_EMAIL` Gmail.
4. You may see a warning *"Google hasn't verified this app"* — that's because the OAuth app is in Testing status. Click **"Advanced"** → **"Go to Kno (unsafe)"**. (It's *your* app; you trust yourself.)
5. Grant the requested scopes.
6. Redirect to `http://localhost:8000/ui/` — you should see a placeholder page with your email in the top-right.

**If the redirect lands somewhere weird:**
- See `redirect_uri_mismatch` from Google → §3.3 step 15 callback URL doesn't match. Edit the OAuth client to add the right one.
- See "Access blocked" → you're not in §3.3 step 8 Test users. Add yourself.
- Lands on `/ui/login` again with an error banner → server logs (`uv run kno serve` terminal) will show why.

**Then connect GitHub:**

1. Navigate to `http://localhost:8000/ui/connections`.
2. Click **"Connect with GitHub"**.
3. GitHub asks you to authorize Kno with the `repo` scope.
4. Approve.
5. Redirect back to `/ui/connections` showing GitHub as connected — the connection's default label is your GitHub login (e.g. `dvhthomas`); you can rename it inline.

**To add another GitHub account later** (e.g. you're a member of `alwaysmap-org` and want Kno to access org repos that your personal account can't):
- Sign out of GitHub in the browser, sign back in with the other account.
- Click **"+ Connect another GitHub account"** at `/ui/connections`.
- New OAuth flow with the second account → second `service_connections` row written.
- Both accounts are now selectable per workflow (per ADR-0019 §2.5).

**Verify the token actually works:**

```bash
# Check that service_connections has a row
sqlite3 data/kno.db "SELECT user_id, provider, connection_label, connection_kind, length(access_token_enc) FROM service_connections;"
```

Expected: one row, `provider=github`, `connection_kind=oauth`, `length > 0` (the encrypted token).

---

## 7. First chat turn

1. `http://localhost:8000/ui/chat`.
2. Workflow picker (top of page) — pick `default`. (`flow-coach` and `kb-qa` aren't useful yet because no KB and no flowmetrics MCP wired in Phase 0.)
3. Type: **"Hey Kno, my name is Dylan. Remember that."**
4. Hit Enter.

**Expected:**
- Response streams via SSE.
- The agent likely calls the `remember_fact` MCP tool with `key=name`, `value=Dylan`. You'll see this in the streaming UI as a tool-call block.
- Final response confirms the fact was remembered.

**Verify the fact was actually stored:**
```bash
sqlite3 data/kno.db "SELECT key, value FROM semantic_facts;"
```
Expected: one row, `name | Dylan`.

**Verify cost was logged:**
```bash
sqlite3 data/kno.db "SELECT model, tokens_in, tokens_out, cost_usd FROM model_calls ORDER BY id DESC LIMIT 5;"
```
Expected: rows from this turn (typically a haiku router call + sonnet synth calls).

**The daily-driver smoke test** (the real proof Kno works):
1. Stop the server (Ctrl-C in the `uv run kno serve` terminal).
2. Restart it: `uv run kno serve`.
3. Reopen `/ui/chat`.
4. **Click your previous thread** in the sidebar.
5. Type: **"Who am I?"**
6. Response should say *"You're Dylan"* (or equivalent).

If that works end-to-end, your Kno is real.

---

## 8. Backup, restore, wipe, export

Four commands cover the data-portability lifecycle. Each has a distinct purpose; don't confuse them.

| Command | Purpose | Format | Reversible? |
|---|---|---|---|
| `kno backup` | Restore Kno from this archive | Opaque tarball (SQLite + `data/` files) | yes — `kno restore` |
| `kno restore` | Restore Kno from a backup | — | yes — back up first |
| `kno wipe` | Delete user data by category | n/a — destructive | no (backup first) |
| **`kno export`** | **Read your data outside Kno** | **Human-readable archive (markdown + JSON + CSV)** | n/a — read-only |

### Backup

Full — SQLite snapshot + all of `data/`:

```bash
uv run kno backup
# → ./kno-backup-2026-05-13-1700.tar.gz
```

Config-only — just `data.seed/`-style files, no operational state:

```bash
uv run kno backup --config-only
# → ./kno-config-2026-05-13-1700.tar.gz
```

The full backup uses `VACUUM INTO` for a consistent SQLite snapshot — safe to run while the server is running.

### Restore

```bash
uv run kno restore ./kno-backup-2026-05-13-1700.tar.gz
```

Safety: prompts before clobbering an existing `data/`. Run with `--force` to skip the prompt.

### Export — human-readable

Different from backup. **Backup is for restoring Kno; export is for reading your data outside Kno.** Use export to:
- Archive your conversation history before leaving Kno (or just for posterity).
- Grep your entire chat history with `ripgrep`.
- Import facts/conversations into a different tool.
- Hand your data to someone you trust (e.g. a researcher with permission).

```bash
# Everything, default tarball
uv run kno export
# → ./kno-export-2026-05-13-1700.tar.gz

# Specific category
uv run kno export --category conversations
uv run kno export --category kb
uv run kno export --category semantic-facts
uv run kno export --category connections

# As a directory rather than tarball (handy for grepping in place)
uv run kno export --format directory --output ~/Documents/kno-export-may-13/
```

**What's in the archive:**

```
kno-export-2026-05-13-1700/
├── README.md                                  ← machine-generated overview
├── conversations/
│   ├── 2026-05-12-name-introduction.md        ← one .md per thread
│   ├── 2026-05-13-flow-coach-on-kno.md
│   └── ...
├── semantic_facts.json                        ← your facts
├── kb_sources/
│   └── github-dvhthomas-bitsby-me/
│       ├── _meta.json                         ← repo + sha + ingest history
│       └── chunks/                            ← reconstructed chunk text
├── model_calls.csv                            ← full cost ledger
├── feedback.json                              ← 👍/👎 with comments and run ids
├── connections.json                           ← provider list — NEVER tokens
├── workflows/                                 ← straight copy of data/workflows/
├── agents/
├── skills/
└── evals/
```

**Privacy contract:**
- `connections.json` contains `{provider, connection_label, scopes, created_at, last_used_at}` — never the encrypted token values themselves. Tokens stay in `service_connections` and never leave the SQLite DB.
- Conversations include tool-call args (a `gh_velocity` call's `repo` and `since` are visible) but not decrypted secrets passed through env.
- If you want to share an export with someone, you don't need to scrub tokens — they're not there.

### Wipe

Delete user data by category. Each is hard-delete, not soft-archive.

```bash
# Just conversation history (keeps semantic_facts, KB, workflows, connections)
uv run kno wipe --category conversations --confirm

# Just KB content (keeps everything else)
uv run kno wipe --category kb --confirm

# Just semantic facts (the agent "forgets" your name etc.)
uv run kno wipe --category semantic-facts --confirm

# Everything — clean slate. Connections, conversations, KB, facts, ledger.
uv run kno wipe --category all --confirm
```

`--confirm` is required; without it, the command prints what it would delete and exits.

**Pro tip:** before any `kno wipe`, run **both** `kno backup` (so you can restore if you change your mind) AND `kno export` (so you have a human-readable copy of what's about to be deleted).

---

## 9. Key rotation

Rotate `KNO_TOKEN_ENC_KEY` (the Fernet KEK that encrypts OAuth tokens in `service_connections`).

1. **Backup first.** `uv run kno backup`.
2. **Generate the new key:**
   ```bash
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
3. **Stop the server.**
4. **Set the new key as `KNO_TOKEN_ENC_KEY_NEW` in `.env`**, keep the old as `KNO_TOKEN_ENC_KEY`.
5. **Run rotation:**
   ```bash
   uv run kno rotate-keys
   ```
   This decrypts each `service_connections.*_enc` row under the old KEK and re-encrypts under the new one. Atomic per row.
6. **Update `.env`:** replace `KNO_TOKEN_ENC_KEY` with the new value; remove `KNO_TOKEN_ENC_KEY_NEW`.
7. **Restart the server.**
8. **Verify** by triggering a tool that uses a stored token (e.g. a flow-coach turn that calls GitHub).

If anything goes wrong: restore the backup from step 1.

**When to rotate:** annually as routine; immediately if the key value leaked.

---

## 10. Deploying to Fly.io

### One-time setup

1. Install `flyctl`: `brew install flyctl`.
2. `fly auth login` — opens browser; sign in.
3. From the `kno/` directory: `fly launch --no-deploy`. Pick an app name (e.g. `kno-dylan`). Decline the "deploy now" prompt. This generates `fly.toml`.
4. Create a persistent volume for `data/`:
   ```bash
   fly volumes create kno_data --size 1 --region <your-region>
   ```
5. **Important:** you need a *separate* GitHub OAuth App for prod (per §3.4's wrinkle). Register it now with callback `https://<your-app>.fly.dev/api/auth/github/callback`. Get its client ID/secret.
6. Set Fly secrets — these are the prod equivalents of your local `.env`. **Do not** use your local-dev OAuth values:
   ```bash
   fly secrets set \
     KNO_ADMIN_EMAIL=you@example.com \
     KNO_TOKEN_ENC_KEY=<new fresh Fernet key, NOT your local one> \
     KNO_SESSION_SECRET=<new fresh random string> \
     KNO_GOOGLE_CLIENT_ID=<from §3.3 — same as local IS fine because Google supports multiple redirect URIs> \
     KNO_GOOGLE_CLIENT_SECRET=<same secret> \
     KNO_GITHUB_CLIENT_ID=<from the PROD OAuth App, not local> \
     KNO_GITHUB_CLIENT_SECRET=<from the PROD OAuth App> \
     KNO_ANTHROPIC_API_KEY=<a fresh key dedicated to prod is cleaner>
   ```
   Ollama settings: Ollama doesn't run on Fly (no GPU on the small machine); the prod deploy uses Anthropic only. The fallback story is "Anthropic outage = banner saying unavailable."
7. Deploy:
   ```bash
   fly deploy
   ```
8. Verify:
   ```bash
   curl -s https://<your-app>.fly.dev/api/health | jq .
   ```

### Iteration

```bash
git push                 # triggers CI
# CI runs lint + mypy + tests + evals
# On green, .github/workflows/deploy.yml auto-deploys
```

### Operational tips

- **Tail logs:** `fly logs`.
- **SSH into the machine:** `fly ssh console`.
- **Backup from Fly:** `fly ssh console` then `uv run kno backup --output -` and pipe to a local file. Or use `fly sftp shell` to grab the latest backup tarball.

---

## 11. Adding workflows and skills

Adding a new workflow with zero code (per spec §9):

1. Create the workflow directory:
   ```bash
   mkdir -p data/workflows/my-thing
   ```
2. Write `data/workflows/my-thing/workflow.yaml`:
   ```yaml
   name: my-thing
   description: What this workflow is for.
   kind: chat
   persona: persona.md
   tools:
     allow:
       - mcp:remember_fact
       - mcp:kb_search  # if you have KB content
   ```
3. Write `data/workflows/my-thing/persona.md`:
   ```markdown
   You are <persona>. <Behavior description>.

   {{skill: cite-sources}}
   {{skill: cost-aware-reasoning}}
   ```
4. Reload:
   ```bash
   curl -X POST http://localhost:8000/api/data/reload
   ```
   Or click "Reload data" in `/ui/workflows`.
5. The workflow now appears in `/ui/chat`'s workflow picker.

Adding a new skill:

1. `mkdir -p data/skills/my-skill`
2. Write `data/skills/my-skill/SKILL.md`:
   ```markdown
   ---
   name: my-skill
   description: One-line description.
   version: 1.0
   author: you@example.com
   tags: [tag1, tag2]
   ---

   The body of the skill — what behavior it instructs.
   ```
3. Reload.
4. Reference it in any workflow's persona via `{{skill: my-skill}}`.

---

## 12. Troubleshooting

### "uv: command not found"

You skipped §1. Install uv: https://github.com/astral-sh/uv.

### "Cannot connect to localhost:11434" at boot

Ollama isn't running.
- macOS: `brew services start ollama`, or `ollama serve` in a terminal.
- Verify: `curl http://localhost:11434/api/tags`.

### "redirect_uri_mismatch" at Google login

`KNO_GOOGLE_CLIENT_ID` is for a project whose OAuth client's redirect URI doesn't match what Kno is using. Check §3.3 step 15: exact URL `http://localhost:8000/api/auth/google/callback` for local, or `https://...fly.dev/api/auth/google/callback` for prod.

### "Access blocked: This app's request is invalid" at Google login

You're not on the Test users list. §3.3 step 8.

### GitHub OAuth returns to `/ui/connections` with no row written

Server logs (`uv run kno serve` terminal) show the actual error. Usually one of:
- Client ID/secret mismatch — copied the wrong values from §3.4.
- Callback URL mismatch — same as Google.
- GitHub rate-limited your test attempts — wait 60 seconds.

### "TokenDecryptError" on any API call

Your `KNO_TOKEN_ENC_KEY` changed but you didn't rotate. Either:
- Restore the previous `KNO_TOKEN_ENC_KEY` from your password manager.
- Or run §9 key rotation (requires the *old* key to still be available).
- Or: `uv run kno wipe --category all --confirm` and reconnect everything from scratch.

### Cost suddenly spiked

```bash
sqlite3 data/kno.db \
  "SELECT date(ts) AS day, sum(cost_usd) FROM model_calls GROUP BY day ORDER BY day DESC LIMIT 7;"
```
If one day is an outlier, drill in:
```bash
sqlite3 data/kno.db \
  "SELECT id, model, tokens_in, tokens_out, cost_usd FROM model_calls WHERE date(ts) = '2026-05-13' ORDER BY cost_usd DESC LIMIT 10;"
```
Match the high-cost call ids back to `runs` for context.

### "Hitting per-session budget cap" in chat

The default cap is $0.50/session per ADR-0018. Either:
- Start a new chat (the cap resets per session).
- Or, if you want a higher cap for a specific workflow, edit the workflow YAML to bump `budgets.per_session_usd` (when Phase 2 adds explicit budget config).

### Server boots but `/api/health` returns `{ok: false}`

Look at which subsystem reports failure. Common: `anthropic: failed` from a revoked key, `ollama: failed` from Ollama being down.

### Anything else

1. Check the server logs from the `uv run kno serve` terminal.
2. Search `docs/spec.md` and `docs/adr/` for the term you're confused about.
3. Open an issue with section number + symptom + log excerpt.

---

## 13. Update history

| Date | Change |
|---|---|
| 2026-05-13 | Initial manual. Provider setup detailed; rest of lifecycle skeletal — will sharpen during Phase 0–2 verification. |
