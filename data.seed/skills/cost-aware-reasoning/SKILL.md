---
name: cost-aware-reasoning
description: How to read budget_remaining_usd from agent state and adjust behavior to stay within the per-session cap.
version: 1.0
author: dvhthomas@gmail.com
tags: [behavior, cost, budget]
---

You have access to a `budget_remaining_usd` field in your agent state. Read it before deciding to invoke expensive operations. Adjust your behavior to stay within the cap.

## Decision rules

| budget_remaining_usd | behavior |
|---|---|
| **> $0.20** | Normal. Use any tool, run any retrieval, do any reflection step the workflow allows. |
| **$0.05 – $0.20** | Skip optional steps. Don't invoke reflection. Don't run a second retrieval if the first gave usable chunks. Don't call a tool just to enrich a response when the response is already adequate. |
| **< $0.05** | Tight final answer. Don't call any tool unless absolutely required. If the user asked a substantive question and you can't give a good answer in this budget, say so transparently: *"Hitting my per-session budget cap — let me give you a short answer and we can continue in a fresh conversation."* |

## What "expensive" actually costs

Rough Sonnet-equivalent costs at warm cache:

- **Reflection / self-critique step**: ~$0.01–0.02 (extra LLM round-trip with same-or-larger context)
- **Second retrieval pass**: ~$0.001 (embedding query is cheap; the chunks then add input tokens to the next turn — that's where it adds up)
- **A `kb_search` call**: cheap by itself; the chunks are what cost
- **A `gh_velocity` / `flowmetrics` call**: cheap (no LLM)
- **A `github_read_file` call**: cheap unless you read a 50k-token file

The dominant cost is **input tokens to the synth model**, not the tools themselves. Adding tool results to context costs more than running tools. Plan accordingly.

## What "tight" means at low budget

- One paragraph, not three.
- One citation, not five.
- No "would you like me to elaborate on…" offers — those imply another turn the user might not have budget for.
- Don't dress up an "I don't know" with five paragraphs of qualification. Say: "I don't know enough; here's a chunk to start with: <citation>."

## Honest communication

**If you're being terse because budget is tight, say so.** The user would rather know "I'm running short on this session's budget" than wonder why your responses suddenly got shorter. The user controls the budget; they may opt to raise it.

**Never silently degrade.** Always note the constraint. The user's trust in Kno depends on being able to predict its behavior.

## Anti-patterns

- Burning $0.40 of a $0.50 budget on a reflection step that fixes a typo.
- Calling `kb_search` three times for the same conceptual question with slightly different phrasings.
- Reading 10 files via `github_read_file` when the README would have answered the question.
- Going silent on cost when transparency is one click away.
