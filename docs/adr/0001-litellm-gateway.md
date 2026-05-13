# ADR-0001: LiteLLM as the model gateway

**Status:** Accepted
**Date:** 2026-05-12
**Drafted in phase:** 0 (Foundation)
**Spec refs:** §4 (Tech Stack), §15 (Cost Model), §18 (Cost Model post-rename)
**Related ADRs:** [[0002]] (LangGraph state machine), [[0004]] (prompt cache block ordering), [[0006]] (per-run token cache), [[0015]] (KB substrate)

---

## Context

Kno calls multiple model providers from a single Python server:

- **Anthropic Claude Sonnet 4.6** — primary synthesis model for chat workflows and the synthesizer in Panel-of-Experts.
- **Anthropic Claude Haiku 4.5** — router classifier (every turn), eval-suite judge, panelist responses where structured output is sufficient and Sonnet would be overkill.
- **Anthropic Claude Opus 4.7** — opt-in only for the hardest tasks; rarely used.
- **Ollama `nomic-embed-text`** — embeddings for the KB (local; $0/token).
- **Forward-compat for additional providers** (OpenAI, Gemini, Bedrock) without rewriting call sites.

The runtime needs:

1. **One call surface** so the agent code doesn't branch on provider.
2. **Cost telemetry** wired automatically — every call must produce a `model_calls` row with `tokens_in`, `tokens_out`, `cached_tokens`, `cost_usd`. The cost ledger is the source of truth for the §18 budget caps (per-session, per-user-day, per-user-month, kill-switch).
3. **Retries + fallback** — Anthropic 429 → backoff; if Anthropic is hard-down, fall back to a local Ollama Claude-class model with a warning banner (acceptable degradation for personal-scale use).
4. **Prompt caching** — Anthropic's `cache_control: ephemeral` blocks (5-min TTL) are load-bearing for the cost model. Without them, typical Flow Coach turn cost jumps from $0.010 (warm) to $0.025 (cold).
5. **Per-call configurability** — temperature, max_tokens, model override per workflow.

The cost-of-getting-this-wrong is high: at $30/mo target, a missing cost telemetry hook for a hot path could 2–3× the bill before anyone notices.

## Decision

Adopt **LiteLLM** (`litellm` Python package, current major version pinned in `pyproject.toml`) as the single model-call surface for Kno, with one well-defined escape hatch.

### What goes through LiteLLM

- Every LLM call from `kno.agent.*`, `kno.workflows.*`, `kno.services.evals`, `kno.services.refine`, and `kno.knowledge.embed` is dispatched via `kno.models.client.complete(model_alias, ...)`, which wraps `litellm.acompletion`/`litellm.aembedding`.
- **Routing aliases** live in `kno.models.routing`:
  ```python
  ROUTING = {
      "router":      "anthropic/claude-haiku-4-5",
      "synth":       "anthropic/claude-sonnet-4-6",
      "cheap_synth": "anthropic/claude-haiku-4-5",
      "eval_judge":  "anthropic/claude-haiku-4-5",
      "opus":        "anthropic/claude-opus-4-7",  # opt-in only
      "embed":       "ollama/nomic-embed-text",
  }
  ```
  Workflows refer to aliases, never raw provider strings. Changing a workflow's model is a one-line YAML edit (`model_override: synth: cheap_synth`), not a code change.
- **Success callback** is registered globally (`litellm.success_callback = [write_to_ledger]`) and writes a `model_calls` row per call: `{run_id, message_id, provider, model, tokens_in, tokens_out, cached_tokens, cost_usd, latency_ms, alias_used}`.
- **Failure callback** (`litellm.failure_callback`) writes a `model_calls` row with `status='failed'` and exception class, so failed calls still appear in the ledger (helpful for debugging cost dropouts).

### Escape hatch: anthropic-direct

`kno.models.caching` calls the `anthropic` SDK directly when a call needs **fine-grained `cache_control` block placement** that LiteLLM's translation may not fully preserve. As of the current LiteLLM version, system-prompt `cache_control: ephemeral` blocks survive the gateway in standard arrangements but corner cases (e.g. interleaved tool_use blocks with mid-message cache markers) can be unreliable. Rather than chase a moving target inside LiteLLM, we use the SDK directly for cached calls and still write to the same `model_calls` ledger from our own callback.

The escape-hatch contract:
- Only `kno.models.caching` may import `anthropic` directly. CI enforces with a static check.
- Ledger writes use the same `write_to_ledger(call_event)` function so cost telemetry remains unified.
- Any new cache-block requirements are added to `kno.models.caching` rather than re-routed through LiteLLM.

### Strict dependency scope

- `litellm` only.
- **No `langchain-community`, no chain abstractions.** LiteLLM does not require them; if a transitive pull tries to bring them in, the pin in `pyproject.toml` is tightened to block it.
- LiteLLM versions are pinned exactly (`==`), not range-pinned. Upgrade triggers an ADR and a check that the cost callback signature hasn't moved.

### Provider failover

Configured in `kno.models.routing.FAILOVER`:

```python
FAILOVER = {
    "anthropic/claude-sonnet-4-6": [
        "ollama/llama3.1-70b-instruct",  # local fallback, banner shown
    ],
    "anthropic/claude-haiku-4-5": [
        "ollama/llama3.1-8b-instruct",
    ],
}
```

Failover only triggers on hard outages (5xx from Anthropic for ≥ 30s, or rate-limit storm). The router and chat UI surface a banner: "Anthropic unavailable — using local fallback. Output quality may be reduced." Users can disable failover per-workflow with `model_override.disable_failover: true`.

## Consequences

### Positive

- **One call surface.** Agent code never branches on provider.
- **Cost telemetry is free.** Every model call appears in `model_calls` without per-call bookkeeping. This is the single biggest reason for this decision — manual ledger writes at every call site would be fragile.
- **Model swaps are config-only.** Changing a workflow's synth model from Sonnet to Opus is a YAML edit; no Python touched.
- **Provider portability** for the future. If we ever want to test Bedrock or Gemini, it's an alias entry, not a refactor.
- **Failover for resilience** with degradation transparent to the user.

### Negative

- **Translation layer** between us and Anthropic. We've accepted this and built the escape hatch (`kno.models.caching`) to handle cases where direct SDK use is preferable.
- **Dep churn risk.** LiteLLM updates rapidly. Pinning exact versions + ADR-on-upgrade contains it.
- **Cost-callback semantics drift.** LiteLLM's success-callback signature has changed across versions. Mitigation: a wrapper test that asserts callback payload shape; runs in CI; fails on upgrade if shape moved.
- **Performance overhead.** LiteLLM adds ~5–15ms per call vs raw SDK. Negligible for our use case.

### Operational

- All LiteLLM environment vars (API keys, base URLs) are loaded via `kno.config` (pydantic-settings), never read directly from `os.environ` by call sites.
- Logging level for `litellm.*` loggers is set to `WARNING` by default — LiteLLM's default is verbose and pollutes the structured-log stream. Override via `KNO_LITELLM_LOG_LEVEL` for debugging.
- The `metrics/litellm-callback-shape.json` artifact in `tests/fixtures/` records the current callback payload shape; CI compares on upgrade.

## Alternatives considered

### 1. Roll our own provider abstraction

Write a thin async client per provider with a unified `complete(...)` interface.

**Rejected because:**
- Cost-tracking bookkeeping is non-trivial and easy to miss at call sites.
- Provider failover is non-trivial to implement well (token-aware retries, backoff jitter, etc.).
- LiteLLM has already solved this for hundreds of users; the marginal value of bespoke code is low.

### 2. Use the Anthropic SDK directly + a separate Ollama client

Two clients, conditional branching in agent code.

**Rejected because:**
- No unified cost ledger — we'd write cost rows from two different code paths and the schemas would drift.
- Routing aliases become brittle: every workflow has to know which client to call.
- Provider portability dies.

### 3. OpenAI Agents SDK / OpenAI Assistants API

Use OpenAI's agent framework as the call surface.

**Rejected because:**
- Anthropic-first system. We pay for Claude, not GPT.
- The Assistants API is opinionated around thread/run primitives that conflict with our LangGraph state model.
- Routing aliases would require a translation that's awkward when most calls are Anthropic.

### 4. DSPy

Treat all LLM calls as declarative signatures + compiled prompts.

**Rejected for runtime** (see ADR-to-write for DSPy deferral; spec §22). DSPy may be revisited as an *offline* prompt-optimization tool (per spec §22 + OQ-13), output of which lands as hand-editable `persona.md` / `prompt.md` files — never imported by the runtime.

### 5. CrewAI's `LLM` abstraction

Use CrewAI's built-in LLM wrappers.

**Rejected because:**
- CrewAI's LLM layer is tightly coupled to its agent abstractions, which we don't use (see ADR-0002).
- Pulling in CrewAI just for the LLM layer is dead weight.

## Verification (Phase 0 verification battery)

- Unit test: `kno.models.client.complete("synth", system="...", user="...")` returns a response and writes one row to `model_calls`.
- Unit test: forcing a `LiteLLMException` triggers the failure callback and writes a `status='failed'` row.
- CI static check: only `kno.models.caching` imports `anthropic` directly.
- Cost-callback shape test: payload matches `tests/fixtures/litellm-callback-shape.json`.

## Open questions deferred

- Token-aware **cost-aware retries** (back off when a retry would push the user over budget). Currently retries are unconditional within LiteLLM's defaults. Track as v1.5 if it becomes a problem.
- **Streaming cost reconciliation.** Anthropic's streaming usage reporting is at end-of-stream; our SSE handler captures it. Edge case: client disconnects mid-stream. Currently we charge for what completed; document in §18.
