# Local quickstart — running Kno on your own machine

> **Audience.** Someone with a Mac or Linux laptop and a working brain, who has never set up Kno before.
>
> **Goal.** From a fresh clone of `dvhthomas/kno`, get Kno running locally in under 60 minutes — first chat turn streaming, your name remembered, costs visible in the ledger.
>
> **The path of least resistance.** Once Phase 2's setup wizard ships (`tasks.md` 2.12), most of this doc becomes "run the wizard and skip to §3 (First chat turn)." Until then, sections §2 and §2.appendix walk the manual fallback. Both end at the same place: a populated `.env` and a running Kno.
>
> Operations (deploying, key rotation, backups) live in `docs/ops.md`, not here.

---

## Contents

1. [Prerequisites](#1-prerequisites)
2. [Get the code + first boot](#2-get-the-code--first-boot)
3. [First login + GitHub connection](#3-first-login--github-connection)
4. [First chat turn](#4-first-chat-turn)
5. [Adding workflows and skills](#5-adding-workflows-and-skills)

[**Appendix A — Manual provider setup**](#appendix-a--manual-provider-setup) — what the wizard does, in case the wizard fails, you're doing it by hand, or you're troubleshooting

---

## 1. Prerequisites

You need these tools on your machine. The commands assume macOS with Homebrew or a recent Linux with a package manager.

| Tool | Purpose | macOS install | Verify |
|---|---|---|---|
| **Python 3.12** (via uv) | Kno is Python | `brew install uv` then `uv python install 3.12` | `uv python list` shows 3.12.x |
| **uv** | dep manager + script runner | (covered above) | `uv --version` |
| **Ollama** | embeddings + LLM fallback | `brew install ollama` | `ollama --version` |
| **git** | source control | preinstalled (or `brew install git`) | `git --version` |
| **gh** (GitHub CLI) | handy for `gh repo clone`; not strictly required by Kno | `brew install gh` | `gh --version` |
| **A browser** | the Kno UI lives here | your preference | n/a |

**Linux note:** apt/dnf/pacman equivalents exist for all of the above. uv has a one-line installer at https://github.com/astral-sh/uv.

**Verify all at once:**

```bash
uv --version && ollama --version && git --version && gh --version
```

If any of those say "command not found," install it before moving on.

---

## 2. Get the code + first boot

```bash
git clone https://github.com/dvhthomas/kno.git
cd kno
uv sync
mkdir -p data
uv run kno serve
```

**Path A — Phase 2 shipped (the wizard exists):** the server detects no `.env`, prints

```
setup mode active; visit http://localhost:8000/setup
setup token: <random>
```

…and serves a wizard at `http://localhost:8000/setup`. Open the URL, paste the setup token into the first form, and the wizard walks every provider step-by-step with live inline validation. ~15 minutes. On completion, it writes `.env`, runs migrations, and reloads the server into normal mode. Skip to §3.

**Path B — pre-Phase-2 (or you prefer manual):** the server will fail to boot without `.env`. Follow [**Appendix A**](#appendix-a--manual-provider-setup), populate `.env` by hand, then run:

```bash
uv run alembic upgrade head
uv run kno serve
```

Expected boot output:

```
[info] starting kno-server version=<sha> commit=<sha>
[info] db_integrity_check ok=true
[info] anthropic_probe ok=true model=claude-haiku-4-5
[info] ollama_probe ok=true embed_model=nomic-embed-text chat_model=llama3.1:8b
[info] uvicorn running on http://0.0.0.0:8000
```

If any probe says `ok=false`, see the boot-probe troubleshooting in [Appendix A — Common pitfalls per provider](#common-pitfalls-per-provider).

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

---

## 3. First login + GitHub connection

1. Open `http://localhost:8000/ui/login` in your browser.
2. Click **"Sign in with Google"**.
3. Pick your `KNO_ADMIN_EMAIL` Gmail at Google's consent screen.
4. You may see *"Google hasn't verified this app"* — that's because your OAuth client is in Testing status. Click **"Advanced"** → **"Go to Kno (unsafe)"**. (It's *your* app; you trust yourself.)
5. Grant the requested scopes.
6. Redirect to `http://localhost:8000/ui/` showing your email in the top-right.

**If the redirect lands somewhere weird:**

- `redirect_uri_mismatch` from Google → callback URL in your OAuth client doesn't match Kno's. See [Appendix A §A.3](#a3-google-oauth-client).
- "Access blocked" → you're not on Google's Test users list for the OAuth consent screen. Add yourself.
- Lands on `/ui/login` again with an error banner → server logs (`uv run kno serve` terminal) tell you why.

**Then connect GitHub:**

1. Navigate to `http://localhost:8000/ui/connections`.
2. Click **"Connect with GitHub"**.
3. GitHub asks you to authorize Kno (with the `repo` scope).
4. Approve.
5. Redirect back to `/ui/connections` showing GitHub as connected. Default label is your GitHub login (e.g. `dvhthomas`); rename inline if you want.

**To add another GitHub account later** (e.g. you're a member of `alwaysmap-org` and want Kno to access org repos that your personal account can't):

- Sign out of GitHub in the browser, sign back in with the other account.
- Click **"+ Connect another GitHub account"** at `/ui/connections`.
- New OAuth flow with the second account → second `service_connections` row written.
- Both accounts are now selectable per workflow (per ADR-0019 §2.5).

**Verify the token actually works:**

```bash
sqlite3 data/kno.db "SELECT user_id, provider, connection_label, connection_kind, length(access_token_enc) FROM service_connections;"
```

Expected: one row, `provider=github`, `connection_kind=oauth`, `length > 0`.

---

## 4. First chat turn

1. `http://localhost:8000/ui/chat`.
2. Workflow picker (top of page) — pick `default`. (`flow-coach` and `kb-qa` aren't useful yet in Phase 0; KB content not ingested + flowmetrics MCP not wired.)
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

## 5. Adding workflows and skills

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

## Appendix A — Manual provider setup

> This appendix exists for: (a) pre-Phase-2 work before the wizard ships, (b) the wizard fails on a step and you need underlying detail, (c) you're troubleshooting, (d) you prefer doing it by hand. The post-Phase-2 path is the wizard at `/setup`; treat this appendix as reference, not the primary flow.

The order goes from **simplest** (Anthropic — one click) to **most involved** (GitHub OAuth Apps — you may need two). The wizard walks these in the same order.

By the end you'll have collected **8–10 values** for `.env`. The wizard collects them into `.env` directly; doing it by hand, paste each into a *scratch buffer* and assemble `.env` in [§A.7](#a7-writing-your-env).

### A.1 Anthropic API key

**Purpose.** Kno's chat/synth/router model calls go through Anthropic via LiteLLM. Per ADR-0001.

**Time:** ~3 minutes.

**You will end up with:** `KNO_ANTHROPIC_API_KEY`.

**Steps:**

1. Go to https://console.anthropic.com/.
2. Sign in. If you're on the Max plan, that's the right account — Kno reuses your org's billing.
3. Left nav → **"API keys"** (or top-right gear → API keys).
4. Click **"Create Key"**.
5. Name it `kno-dev` (or `kno-prod` later; one per environment is cleanest).
6. Copy the key starting with `sk-ant-`. **You can't see it again** — save it to your scratch buffer now.
7. Optional but recommended: under **"Workspaces"** or **"Spend limits"**, set a workspace-level monthly cap (e.g. $30) on this key as a hard backstop beyond Kno's own per-session caps.

**Scratch buffer:**
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
Expected: a JSON response with `"content"`. `"error"` means the key is wrong or revoked.

**Common pitfalls:**
- Copying the key with trailing whitespace.
- Putting the key in a public repo or chat. Treat it like a password.

### A.2 Ollama (local)

**Purpose.** (a) Embeddings for KB via `nomic-embed-text`. (b) Chat fallback if Anthropic is unreachable, via `llama3.1:8b` (or `:70b` if RAM permits).

**Time:** ~5 minutes wall (plus ~5–15 minutes of model download).

**You will end up with:** `KNO_OLLAMA_BASE_URL`, `KNO_OLLAMA_EMBED_MODEL`, `KNO_OLLAMA_FALLBACK_CHAT_MODEL`. None are secrets; defaults work for most people.

**Steps:**

1. Start the Ollama service.
   - macOS: `brew services start ollama` (launchd; survives logout).
   - Or interactively: `ollama serve`.
2. Pull the embedding model (~700 MB):
   ```bash
   ollama pull nomic-embed-text
   ```
3. Pull a chat fallback model (~5 GB for 8b, ~40 GB for 70b):
   ```bash
   ollama pull llama3.1:8b
   ```
4. Verify both models are loaded:
   ```bash
   ollama list
   ```
5. Smoke-test embeddings:
   ```bash
   curl -s http://localhost:11434/api/embeddings \
     -d '{"model":"nomic-embed-text","prompt":"hello"}' | head -c 200
   ```
   Expected: JSON with `"embedding":[<floats>]`. `connection refused` = Ollama isn't running.

**Scratch buffer:**
```
KNO_OLLAMA_BASE_URL=http://localhost:11434
KNO_OLLAMA_EMBED_MODEL=nomic-embed-text
KNO_OLLAMA_FALLBACK_CHAT_MODEL=llama3.1:8b
```

**Common pitfalls:**
- Forgetting to start Ollama.
- Mac firewall blocking `localhost:11434`. Allow it.
- Trying to run 70b on a 16 GB RAM machine. Use 8b unless you have ≥64 GB.

### A.3 Google OAuth client

**Purpose.** Identity. Kno uses Google to identify you when you log in to `/ui/`. v1 is single-user but the OAuth flow is the same as multi-user — your `KNO_ADMIN_EMAIL` must match the Google account you log in with.

**Time:** ~10 minutes (Google Cloud Console has multiple confirmation screens).

**You will end up with:** `KNO_GOOGLE_CLIENT_ID`, `KNO_GOOGLE_CLIENT_SECRET`.

**Steps:**

1. Go to https://console.cloud.google.com/.
2. Top-left dropdown → **"New Project"**. Name it `kno-dev` (or reuse one — Google's OAuth client is per-project).
3. Switch to the new project via the top-left dropdown.
4. Left nav → **"APIs & Services"** → **"OAuth consent screen"**.
5. **User type:** **"External"**. Click **"Create"**.
6. **App information:**
   - App name: `Kno` (or `Kno-dev`).
   - User support email: your email.
   - Developer contact email: your email.
   - **"Save and continue"**.
7. **Scopes:** **"Save and continue"** without adding any. (Kno requests scopes in code, not the consent screen.)
8. **Test users:** **"+ Add users"** → add the Gmail you'll log in as. **Required** while the app is in "Testing" status. **"Save and continue"**.
9. **Summary:** **"Back to dashboard"**.
10. Left nav → **"APIs & Services"** → **"Credentials"**.
11. **"+ Create Credentials"** → **"OAuth client ID"**.
12. **Application type:** **"Web application"**. **NOT "Desktop app"** — that's a different OAuth flow Kno doesn't support.
13. **Name:** `Kno (local dev)`.
14. **Authorized JavaScript origins:** leave empty.
15. **Authorized redirect URIs:**
    - **"+ Add URI"** → `http://localhost:8000/api/auth/google/callback`
    - If you're also planning a Fly deploy: **"+ Add URI"** → `https://<your-fly-app>.fly.dev/api/auth/google/callback`. Google supports multiple redirect URIs per client.
16. **"Create"**.
17. Modal appears with **Client ID** and **Client secret**. Copy both.

**Scratch buffer:**
```
KNO_GOOGLE_CLIENT_ID=123456789012-abcdefghij...apps.googleusercontent.com
KNO_GOOGLE_CLIENT_SECRET=GOCSPX-XXXXXXXXXXXX
```

**Common pitfalls:**
- "Desktop app" instead of "Web application" → `redirect_uri_mismatch` at login time. Edit-and-fix isn't possible; you'd have to create a new client.
- Forgetting Test users → "Access blocked" on login.
- Redirect URI typo → `redirect_uri_mismatch`. Must match Kno's actual callback path exactly.
- Wrong project → client ID lives in a project Kno isn't using.

**Verification (post-`.env` + Kno running):** see §3 First login above.

**→ One-time deployer task.** After this, adding another Google account inside Kno is a single button click in `/ui/connections`.

### A.4 GitHub OAuth Apps

**Purpose.** Two MCP servers need GitHub-authenticated access: `github` (read repos for Flow Coach + KB ingestion) and `flowmetrics` (reads via `gh` CLI inheriting `GH_TOKEN` — see ADR-0019 §3).

**Time:** ~7 minutes per OAuth App. You may need **two** (one for local dev, one for production).

**You will end up with:** `KNO_GITHUB_CLIENT_ID`, `KNO_GITHUB_CLIENT_SECRET`. (Or two pairs if you set up dev + prod.)

**The GitHub wrinkle.** Unlike Google, a GitHub OAuth App allows **exactly one callback URL**. If you want to run Kno both locally and on Fly, register **two separate OAuth Apps**:

- **App #1:** `Kno (local dev)` — callback `http://localhost:8000/api/auth/github/callback`. Client ID/secret → local `.env`.
- **App #2:** `Kno (prod)` — callback `https://<your-fly-app>.fly.dev/api/auth/github/callback`. Client ID/secret → Fly secrets (per `docs/ops.md`).

If you're only running locally for now, do just App #1; defer prod until you deploy.

**Alternative — GitHub App primitive** (not "OAuth App"): supports multiple callback URLs + finer-grained permissions. **Don't** for v1 — heavier than needed, different auth flow.

**Steps (for one OAuth App):**

1. https://github.com/settings/developers
2. Left nav → **"OAuth Apps"** (NOT "GitHub Apps" — they're right next to each other).
3. **"New OAuth App"** (top-right).
4. **Application name:** `Kno (local dev)` or `Kno (prod)`.
5. **Homepage URL:** `http://localhost:8000` or `https://<your-fly-app>.fly.dev`.
6. **Application description:** anything; "Personal Kno deployment" is fine.
7. **Authorization callback URL:**
   - Local: `http://localhost:8000/api/auth/github/callback`
   - Prod: `https://<your-fly-app>.fly.dev/api/auth/github/callback`
   - **This is the most error-prone field.** Path is `/api/auth/github/callback`, not `/auth/callback`, not `/api/github/callback`.
8. **Enable Device Flow:** unchecked.
9. **"Register application"**.
10. On the result page:
    - **Client ID:** copy from the top.
    - **Client secrets:** scroll down → **"Generate a new client secret"**. Appears once; copy immediately.

**Scratch buffer:**
```
# Local-dev OAuth App
KNO_GITHUB_CLIENT_ID=Iv1.XXXXXXXXXXXX
KNO_GITHUB_CLIENT_SECRET=XXXXXXXXXXXXXXXXXXXXXXXX
```

(Prod App credentials go to Fly secrets per `docs/ops.md`.)

**Common pitfalls:**
- Wrong callback URL (most common).
- Using a single OAuth App for local + prod → second deployment fails `redirect_uri_mismatch`.
- Confusing "OAuth App" with "GitHub App" in the nav.
- Lost the client secret → regenerate; update everywhere it's used.

**Verification (post-Kno-running):** see §3 first login above.

**→ One-time deployer task.** After this, adding another GitHub account inside Kno is a single button click in `/ui/connections`.

### A.5 Locally-generated secrets

These never touch a provider's website. Random values generated on your own machine.

**You will end up with:** `KNO_TOKEN_ENC_KEY` (Fernet KEK that encrypts OAuth tokens at rest per ADR-0019) and `KNO_SESSION_SECRET` (HMAC for signed session cookies).

**Steps (after `uv sync` so `cryptography` is in the venv):**

1. Generate the Fernet KEK:
   ```bash
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
2. Generate the session secret:
   ```bash
   uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

**Scratch buffer:**
```
KNO_TOKEN_ENC_KEY=<from step 1>
KNO_SESSION_SECRET=<from step 2>
```

**Common pitfalls:**
- Reusing the same value for both. They have different purposes; generate each freshly.
- Generating new values without rotating existing encrypted data. If you've already run Kno once and have rows in `service_connections`, a new `KNO_TOKEN_ENC_KEY` makes them unreadable. See `docs/notes/data-management.md` → "Key rotation" before changing.
- Committing to git. **Never.** `.env` is gitignored; verify with `git status` before commit.

### A.6 Honeycomb (optional)

**Purpose.** OpenTelemetry traces for every agent run. Useful for debugging cost or latency anomalies. **Skip for first-time setup.**

**Time:** ~3 minutes.

**You will end up with (optional):** `KNO_HONEYCOMB_KEY`, `KNO_HONEYCOMB_DATASET`.

**Steps:** https://ui.honeycomb.io/ → sign up (free tier) → API key from account settings → pick a dataset name (e.g. `kno-dev`).

If unset, Kno logs structured events to stderr; tracing exporter no-ops; no errors.

### A.7 Writing your `.env`

You have a scratch buffer with **8–10 values**. Assemble the real `.env`:

```bash
cp .env.example .env
$EDITOR .env
```

Walk through `.env.example` top to bottom. Mapping:

| Section in `.env.example` | What to fill | Source |
|---|---|---|
| **Owner & encryption** | `KNO_ADMIN_EMAIL` | The Gmail you used in §A.3 step 8 |
|  | `KNO_TOKEN_ENC_KEY` | §A.5 step 1 |
|  | `KNO_SESSION_SECRET` | §A.5 step 2 |
| **Google OAuth** | `KNO_GOOGLE_CLIENT_ID` | §A.3 |
|  | `KNO_GOOGLE_CLIENT_SECRET` | §A.3 |
| **GitHub OAuth** | `KNO_GITHUB_CLIENT_ID` | §A.4 (local app) |
|  | `KNO_GITHUB_CLIENT_SECRET` | §A.4 (local app) |
| **Anthropic** | `KNO_ANTHROPIC_API_KEY` | §A.1 |
| **Ollama** | defaults work if you used the standard models | §A.2 |
| **Database** | default works | — |
| **Server** | defaults work | — |
| **Observability** | `KNO_HONEYCOMB_KEY` if set up | §A.6 (or leave empty) |
| **Dev / test flags** | leave defaults | — |

**Final sanity check (before first boot):**

```bash
grep -E '^KNO_[A-Z_]+=$' .env
```

Expected: returns **nothing**. Any line like `KNO_FOO=` means you missed it.

```bash
grep -c '^[A-Z]' .env
```

Expected: 14–16 non-comment lines (depending on whether you set Honeycomb).

**Common pitfalls:**
- **Quoting.** Don't wrap values in quotes unless they contain spaces (none of Kno's values should).
- **Trailing whitespace.** Some editors add a space; the Fernet KEK breaks.
- **Wrong account on `KNO_ADMIN_EMAIL`.** Must match the Google account you log in with, exactly, case-sensitive.

### Common pitfalls per provider — boot-time

If any of the four boot-time probes fails:

- `anthropic_probe ok=false` → key wrong or revoked. Re-verify with §A.1's curl test.
- `ollama_probe ok=false embed=false` → Ollama isn't running or embed model isn't pulled. `ollama list` to check; `ollama pull nomic-embed-text` if missing.
- `ollama_probe ok=false chat=false` → fallback chat model not pulled. `ollama pull llama3.1:8b`.
- `db_integrity_check ok=false` → `data/kno.db` is corrupted (rare on first boot). Delete it (`rm data/kno.db`) and rerun `uv run alembic upgrade head`.
