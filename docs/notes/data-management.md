# Data management — backup, restore, wipe, export, key rotation

> **Audience.** You, using Kno daily, wanting to know how to safely move your data around.
>
> **Scope.** Five CLI commands and the operational discipline around them. Not setup (see `docs/notes/setup/local-quickstart.md`); not platform deploys (see `docs/ops.md`).
>
> **Pro tip up front.** Backup before wipe. Export before any "I might want to read this later in a different tool."

---

## Four-command map

Four commands cover the data-portability lifecycle. Each has a distinct purpose; don't confuse them.

| Command | Purpose | Format | Reversible? |
|---|---|---|---|
| `kno backup` | **Restore Kno from this archive** | Opaque tarball (SQLite + `data/` files) | yes — `kno restore` |
| `kno restore` | Restore Kno from a backup | — | yes — back up first |
| `kno wipe` | Delete user data by category | n/a — destructive | no (backup first) |
| **`kno export`** | **Read your data outside Kno** | **Human-readable archive (markdown + JSON + CSV)** | n/a — read-only |

Plus one related security operation:

| Command | Purpose |
|---|---|
| `kno rotate-keys` | Rotate `KNO_TOKEN_ENC_KEY` (Fernet KEK that encrypts OAuth tokens) |

---

## Backup

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

**When to backup:**
- Before any `kno wipe`.
- Before any `kno rotate-keys`.
- Before any `kno restore` (yes; back up the existing state before clobbering).
- As a routine — daily on Fly via the integrity-check cron, weekly locally as a habit.

---

## Restore

```bash
uv run kno restore ./kno-backup-2026-05-13-1700.tar.gz
```

Safety: prompts before clobbering an existing `data/`. Run with `--force` to skip the prompt.

---

## Export — human-readable

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

---

## Wipe

Delete user data by category. Each is **hard-delete**, not soft-archive.

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

`--confirm` is required; without it, the command prints what *would* be deleted and exits.

**Pro tip:** before any `kno wipe`, run **both** `kno backup` (so you can restore) AND `kno export` (so you have a human-readable copy of what's about to be deleted).

---

## Key rotation

Rotate `KNO_TOKEN_ENC_KEY` — the Fernet KEK that encrypts OAuth tokens in `service_connections`. Per ADR-0018 §2.3 item 7.

**When to rotate:** annually as routine; immediately if the key value leaked.

**Procedure:**

1. **Backup first.**
   ```bash
   uv run kno backup
   ```

2. **Generate the new key:**
   ```bash
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

3. **Stop the server** (Ctrl-C in the `uv run kno serve` terminal).

4. **Set the new key as `KNO_TOKEN_ENC_KEY_NEW` in `.env`**, keep the old as `KNO_TOKEN_ENC_KEY`.

5. **Run rotation:**
   ```bash
   uv run kno rotate-keys
   ```
   Decrypts each `service_connections.*_enc` row under the old KEK and re-encrypts under the new one. Atomic per row. Per-row failures roll back independently.

6. **Update `.env`:** replace `KNO_TOKEN_ENC_KEY` with the new value; remove `KNO_TOKEN_ENC_KEY_NEW`.

7. **Restart the server.**

8. **Verify** by triggering a tool that uses a stored token (e.g. a flow-coach turn that calls GitHub).

If anything goes wrong: restore the backup from step 1.

---

## Common pitfalls

### "TokenDecryptError" on any API call

Your `KNO_TOKEN_ENC_KEY` changed but you didn't rotate. Either:

- Restore the previous `KNO_TOKEN_ENC_KEY` from your password manager.
- Or run the key-rotation procedure above (requires the *old* key still to be available).
- Or — last resort — `uv run kno wipe --category all --confirm` and reconnect everything from scratch.

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

Default cap: $0.50/session per ADR-0018. Either:

- Start a new chat (the cap resets per session).
- Or, if you want a higher cap for a specific workflow, edit the workflow YAML to bump `budgets.per_session_usd` (Phase 2 adds explicit budget config to workflow YAML).

### Backup is huge

Most likely cause: the KB content is large. `du -sh data/kb/` to check. Options:

- Use `kno backup --config-only` for a small, fast, no-KB backup (KB chunks are regenerable from sources anyway).
- For a full backup, plan on the size.

### Export takes forever

LLM-as-judge generates conversation titles for `conversations/*.md` filenames on first export. Subsequent exports cache them. First export against months of conversations may take a minute or two.
