# Kno

Personal agent harness. Run agentic workflows from a web browser; depend on it daily.

> **Status:** Pre-implementation. Spec v0.9 with **Kno-Lite v1 scope** per [ADR-0018](docs/adr/0018-kno-lite-scope.md).
>
> **Framing:** a small daily-driver personal AI you built yourself, refine over time, and depend on — not a corporate/team product. ("Pi.ai play.")

---

## Where do I start?

| If you want to… | Read this |
|---|---|
| **Run Kno on my laptop for the first time** | [`docs/notes/setup/local-quickstart.md`](docs/notes/setup/local-quickstart.md) — prerequisites, first boot, first login, first chat |
| **Deploy Kno to a server (Fly.io)** | [`docs/ops.md`](docs/ops.md) — platform setup, deploy pipeline, off-machine backup, custom domain, ops |
| **Back up, restore, wipe, export, or rotate keys** | [`docs/notes/data-management.md`](docs/notes/data-management.md) — five-command map + procedures |
| **Understand how Kno is designed** | [`docs/spec.md`](docs/spec.md) — full design vision (v2 roadmap); v1 scope per ADR-0018 |
| **See the v1 build plan** | [`docs/plan.md`](docs/plan.md) — 3 phases + pre-flight, ~6 weeks |
| **See the operational task list** | [`docs/tasks.md`](docs/tasks.md) — what to build, in dependency order |
| **Understand individual design decisions** | [`docs/adr/`](docs/adr/) — 19 ADRs (8 drafted, 11 to draft) |
| **Resolve a specific open question** | [`docs/notes/`](docs/notes/) — research + decision notes (e.g. [`gh-velocity.md`](docs/notes/gh-velocity.md)) |

---

## What is Kno?

A single-user agent harness. v1 (Kno-Lite) ships three workflows:

1. **Default chat** — talk to Kno with persistent memory (it remembers your name across sessions) and citation discipline
2. **Flow Coach** — Vacanti-style flow-metrics analysis of your GitHub repos via [`dvhthomas/flowmetrics`](https://github.com/dvhthomas/flowmetrics) (Monte Carlo when-done, aging WIP, cycle-time p85, throughput)
3. **KB-QA** — cited answers from your own Hugo-built sites (`dvhthomas/`, `calcmark/`, `alwaysmap/` GitHub orgs)

Single user (you). Browser-canonical UI. Runs at `http://localhost:8000` on your laptop or `https://<your>.fly.dev` on Fly.io — same code. Improves measurably with use: 👍 / 👎 feedback + per-workflow eval suite + LLM-assisted prompt refinement at `/admin/refine`.

Deferred to v2 (per ADR-0018): Panel of Experts (multi-agent composition), additional KB sources beyond Hugo (Drive, uploads, generic GitHub), multi-user, Slack adapter, scheduled triggers.

---

## Stack at a glance

Python 3.12 · `uv` · FastAPI + HTMX + Alpine · LangGraph (state machine) · LiteLLM (model gateway) · Anthropic Claude (Sonnet for synth, Haiku for router) · Ollama (`nomic-embed-text` embeddings + `llama3.1:8b` chat fallback) · SQLite + sqlite-vec + FTS5 · MCP (tools) · Fly.io (hosting)

See [spec §4](docs/spec.md) for the rationale on each choice. Substrate portability (SQLite ↔ Postgres+pgvector) is documented in [ADR-0015](docs/adr/0015-kb-substrate-portability.md).

---

## Status

| | |
|---|---|
| Spec | **v0.9** ([change log](docs/spec.md#24-change-log)) |
| Scope | **Kno-Lite** per [ADR-0018](docs/adr/0018-kno-lite-scope.md) |
| Phase | Pre-flight (no production code yet; ~770 lines of skills + .env example + notes) |
| ADRs drafted | 8 of 19 (0001–0003, 0010, 0011, 0015, 0018, 0019) |
| v1 calendar | ~6 weeks from start of Phase 0 |
| Target Anthropic spend | <$30/mo for normal daily-driver use |

Real, blocking pre-flight work: see [`docs/tasks.md`](docs/tasks.md) Pre-flight section.

---

## Inspirations

- Will Larson, [_Agents_ series](https://lethain.com/agents-series/) — workflows + skills + virtual files + refinement loops + the "agent is just a loop" framing
- Antonio Gulli, _Agentic Design Patterns_ — memory taxonomy (working / semantic / episodic / procedural), multi-agent patterns, human-in-the-loop checkpoints
- [agentic-patterns.com](https://www.agentic-patterns.com/) — 171-pattern catalog; especially _Filesystem-Based Agent State_, _Progressive Disclosure_, _Episodic Retrieval & Injection_
- Daniel Vacanti, _Actionable Agile Metrics for Predictability_ — the flow-metrics framework Flow Coach speaks
- Inflection's Pi.ai — the framing of "personal AI you depend on"

---

## License

TBD before public release.
