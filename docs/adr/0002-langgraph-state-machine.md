# ADR-0002: LangGraph as the agent state machine

**Status:** Accepted
**Date:** 2026-05-12
**Drafted in phase:** 0 (Foundation)
**Spec refs:** §4 (Tech Stack), §7 (Architecture), §9 (Agents/Skills/Workflows/Sub-agents), §11 (Memory), §13 (Action Approval), §14 (Observability/Feedback/Refinement)
**Related ADRs:** [[0001]] (LiteLLM gateway), [[0011]] (checkpointer colocation), [[0016]] (interrupt resume semantics)

---

## Context

Kno's agent runtime must support six load-bearing capabilities:

1. **Multiple node types in one run** — router → retrieve → synth ↔ tools → (reflect) → end. Each node is an async function that mutates a typed state.
2. **Concurrent fan-out** for Panel-of-Experts: 5 panelist sub-graphs run in parallel; a synthesizer reduces their outputs.
3. **Durable state across requests** — a long Panel run or a paused-for-approval session must survive process restarts.
4. **Human-in-the-loop interrupts** for the §13 approval gates: when the agent tries to call a non-`read` tool, the run pauses, the UI surfaces the pending action, the user approves/denies, and the run resumes from exactly where it left off. This is non-negotiable per [[feedback-strong-approval]].
5. **Sub-agent spawning** — a parent graph invokes a child graph via `subagent(name, prompt, files)`, the child runs in its own isolated context, returns a tool-result to the parent.
6. **Replayability for debugging** — every state transition checkpointed so `/ui/runs/<id>` can render the full timeline and `/admin/refine` can feed log windows to Claude for prompt-revision proposals.

These six capabilities — together — rule out a hand-rolled async loop. The hardest one is (4): human-in-the-loop interrupts require either bespoke state-pickling machinery or a framework that provides it as a primitive.

Additional constraints:

- **Python-only** (per spec A14).
- **SQLite-friendly** (per spec A3) for v1; migration to Postgres documented (ADR-0011, ADR-0015).
- **MCP-first tool integration** (per spec A5). Tools must be addressable as graph nodes/edges, not embedded as inline Python.
- **Cost-conscious** — the framework must not add significant per-call overhead.

## Decision

Adopt **LangGraph** as the agent state machine, with **hard-limited LangChain ecosystem dependencies**.

### Packages used

```toml
# pyproject.toml — pinned exact versions
langgraph = "==<pin>"
langgraph-checkpoint-sqlite = "==<pin>"   # v1
# langgraph-checkpoint-postgres — added only on Neon migration (see ADR-0015)
langchain-core = "==<pin>"                # transitive; minimal surface
```

**Explicitly NOT used** (and blocked via dep audit):

- `langchain-community` — too broad, churns fast, brings in dozens of integrations we don't want.
- `langchain` (the umbrella package) — superset of `langchain-core` + abstractions we replace ourselves.
- `langchain-anthropic` chain helpers — we go through LiteLLM ([[0001]]).
- LangChain's memory/retriever/agent abstractions — we have our own (`kno.memory.*`, `kno.knowledge.*`).

### Shape of usage

A workflow compiles into a `StateGraph[AgentState]`. The state is a TypedDict:

```python
# src/kno/agent/state.py
class AgentState(TypedDict):
    messages: list[Message]
    workflow_slug: str
    workflow_version_id: int
    user_id: str
    run_id: str
    lane: NotRequired[Lane]            # set by router; absent for kind=panel
    retrieved_chunks: NotRequired[list[Chunk]]
    virtual_files: NotRequired[dict[str, VirtualFile]]
    budget_used_usd: float
    pending_approval: NotRequired[PendingApproval]
    panel_artifact: NotRequired[VirtualFileRef]    # kind=panel only
    panelist_responses: NotRequired[list[PanelistResponse]]  # kind=panel only
```

Nodes are async functions:

```python
async def router_node(state: AgentState) -> AgentState:
    lane = await classify(state["messages"][-1])
    return {"lane": lane}  # LangGraph merges into state
```

Graph topology per workflow kind:

```
kind: chat       →   START → retrieve → synth → tools(loop) → END
                                          │
                                          └─► subagent (optional, ADR-future)

kind: panel      →   START → fetch_artifact → ┬─► panelist_1 ─┐
                                              ├─► panelist_2 ─┼─► synthesizer → END
                                              ├─► panelist_3 ─┤
                                              ├─► panelist_4 ─┤
                                              └─► panelist_5 ─┘
                                              (concurrent fan-out via parallel branches)

kind: pipeline   →   deferred to v2
```

Compaction node (Larson 80% window) runs as a conditional edge: if `state.token_count > 0.8 * model_window`, the next edge target is `compact`, else the originally-routed target.

### Checkpointing

`langgraph-checkpoint-sqlite`'s `SqliteSaver` writes a checkpoint to the same `data/kno.db` file after every node completes (see [[0011]] for colocation rationale). Each `thread_id` = our `run_id`. A run can be resumed by `app.invoke(None, config={"configurable": {"thread_id": run_id}})`.

### Human-in-the-loop interrupts

The `tools` node uses `interrupt_before` semantics:

```python
graph.add_node("tools", tools_node)
# At compile:
app = graph.compile(
    checkpointer=saver,
    interrupt_before=["tools"]  # always pause; the node itself decides whether to proceed
)
```

The `tools_node` reads `state.action_category` (resolved at the previous synth's tool_use) and:
- If `read` or `internal_write` → executes immediately (the "always pause" is a no-op interrupt that resumes itself).
- If `external_write` / `external_messaging` / `irreversible` → sets `state.pending_approval` and the SSE handler emits `pending_approval` to the client; LangGraph remains paused until `app.invoke(Command(resume=decision), ...)`.

This pattern (always interrupt, then conditionally auto-resume) is borrowed from Gulli ch. 5 "Human-in-the-loop checkpoints" and validated against our §13 design. See [[0016]] for the resume semantics when an interrupt outlives a process restart or the user takes hours to decide.

### Sub-agents (deferred to a future ADR)

Sub-agent spawning (per spec §9.7) maps to LangGraph's `Send` API for child-graph dispatch. v1 ships the *mechanism* but no v1 workflow actually uses it (Larson is skeptical; no canonical flow requires it; see spec §9.7).

### Strict dep-audit enforcement

A CI check imports `pkg_resources` to walk the dependency tree and fails the build if any of the blocked package patterns (`langchain` umbrella, `langchain-community`, `langchain-experimental`, etc.) appear. The check runs on every PR.

## Consequences

### Positive

- **Human-in-the-loop is a primitive**, not a project. The approval-gate design in §13 maps 1:1 onto `interrupt_before` + `Command(resume=...)`. Without this, building gates that survive restarts would be weeks of bespoke pickling work.
- **Concurrent fan-out for panels** is one line (`branch_to=[panelist_1, panelist_2, ...]`). The §9.4 panel runtime becomes a thin orchestrator.
- **Checkpointing** gives us free replayability — `/ui/runs/<id>` timeline is just iterating the checkpointer's history for a `thread_id`.
- **TypedDict state** + `mypy --strict` catches a class of node-contract bugs at typecheck time. Worth more than the dep weight.
- **Tested, maintained, popular.** Bus factor is fine.

### Negative

- **LangChain blast radius.** Even with strict dep limits, `langchain-core` is in the tree. Upgrades to LangGraph sometimes float `langchain-core` and we have to verify nothing we depend on moved.
- **Framework conventions to learn.** Node functions return state deltas, not full states. `Annotated[..., add_messages]` reducers are subtle. Onboarding cost: ~1 day to internalize.
- **Edge cases at the seams.** Concurrent branches that all write to the same state key need an explicit reducer; default-merge is "last wins" which is wrong for panel results (we want concatenation). Mitigation: use `operator.add` reducer on `panelist_responses`.
- **Version churn.** LangGraph is still pre-1.0 in spirit even if numbered higher. We pin exactly and ADR every upgrade.

### Operational

- The `langgraph` and `langgraph-checkpoint-*` versions are pinned exactly. Any upgrade triggers an ADR + a re-run of the Phase 0 verification battery.
- The CI dep-audit check is non-skippable; PRs that pull in blocked packages are rejected with a clear message.
- The TypedDict state schema is versioned. A schema change is a migration (new fields are NotRequired and back-fill in the read path; removed fields stay declared with a deprecation comment for one release).

## Alternatives considered

### 1. Hand-rolled async loop

Build our own `while not done: ...` with state held in a dataclass and pickled to SQLite for checkpoints.

**Rejected because:**
- Human-in-the-loop interrupts require state pickling across process restarts, which is non-trivial to do safely (pickle is fragile; structured state with explicit migration is safer; LangGraph already does this).
- Concurrent fan-out for panels would require our own task-spawn + state-merge primitives.
- Replayability — being able to step through a run's history — is a meaningful debugging feature that LangGraph gives us for free.
- Total dev time savings: weeks.

### 2. OpenAI Agents SDK / Assistants API

Use OpenAI's thread/run primitives even though our models are Anthropic.

**Rejected because:**
- Vendor-locked to OpenAI's runtime; our models are elsewhere.
- The Assistants thread model conflicts with our notion of `runs` (one workflow invocation = one `run`).
- Interrupt semantics in the Assistants API are weaker than LangGraph's.

### 3. CrewAI

Use CrewAI's `Crew` + `Agent` + `Task` primitives.

**Rejected because:**
- CrewAI is opinionated around "a crew of agents collaborating on a task" — its sweet spot is closer to our `kind: panel` but rigid in the other directions.
- `kind: chat` is awkward in CrewAI's model.
- Human-in-the-loop is less mature than LangGraph's.
- We'd lose the typed-state benefit.

### 4. smolagents (Hugging Face)

Lightweight agent framework.

**Rejected because:**
- Newer; less mature human-in-the-loop story.
- Checkpointer ecosystem is thin.
- LangGraph's mindshare means our Q&A and reference material are more abundant.

### 5. Microsoft Agent Framework

Considered for completeness.

**Rejected because:**
- Less Pythonic; primary documentation skews C#.
- LangGraph adequately covers the same primitives with a more native Python feel.

### 6. Just LangChain (no LangGraph)

Use LangChain `Chain`s composed manually.

**Rejected because:**
- The pre-graph LangChain model is fundamentally a DAG of static operations. Our control flow (router-based branching, tool loops, panel fan-out) requires the explicit graph model LangGraph provides.
- LangChain's chains + manual orchestration would reintroduce the very state-machine complexity LangGraph was built to abstract.

## Verification (Phase 0 verification battery)

- Smoke test: build a 2-node graph (echo → echo) with a `SqliteSaver` checkpointer; run with `thread_id="test-1"`; assert two checkpoint rows in DB.
- Interrupt test: build a 2-node graph with `interrupt_before=["second"]`; invoke; assert state is paused after `first`; resume with `Command(resume=None)`; assert completion.
- Concurrency test: a fan-out graph with 3 parallel branches each appending to a list with `operator.add` reducer; assert all 3 appear in final state in stable order.
- Dep-audit test: `pytest tests/static/test_deps.py` walks `pkg_resources` and asserts no blocked packages present.
- Schema test: AgentState TypedDict matches the documented v1 shape; new fields are `NotRequired`.

## Open questions deferred

- **Sub-agent invocation semantics.** v1 ships the mechanism; no v1 workflow uses it. A future ADR formalizes the `subagent(name, prompt, files)` tool's wire shape, the parent-child state boundary, and budget accounting.
- **Interrupt-on-restart durability.** What happens when the FastAPI process restarts while a run is awaiting approval? The checkpoint is durable; `kno-cli runs pending` should list it on next boot. See [[0016]] for full specification.
- **Reducer hygiene for panel results.** v1 uses `operator.add` for `panelist_responses`. If we ever support a debate variant (deferred to v2), the reducer needs to support round-replacement, not concatenation. Track at variant-introduction time.
