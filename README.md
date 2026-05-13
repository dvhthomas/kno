# kno

Personal agent platform. CLI: `kno`.

Status: pre-implementation. See [`docs/spec.md`](docs/spec.md) for the v0.1 spec.

## Quick links

- **Spec:** [`docs/spec.md`](docs/spec.md)
- **Plan:** [`docs/plan.md`](docs/plan.md) — produced after spec approval
- **ADRs:** [`docs/adr/`](docs/adr/)
- **Issues:** GitHub (label-driven flow metrics — see spec §12)

## Use cases (v1)

1. **Flow Coach** — Conversational Vacanti-style metrics on my GitHub repos.
2. **Personal Knowledge Base** — Q&A over `bitsby.me`, `calcmark.org`, `recipes4me.org`.
3. **Co-Planner** — Interactive planning grounded in `calcmark.org`.

## Stack at a glance

Python 3.12 · `uv` · FastAPI · HTMX · Postgres+pgvector · MCP · Anthropic (Claude) + Ollama (embeddings) · Fly.io
