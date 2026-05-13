---
name: cite-sources
description: Require explicit, verifiable citations in every response that draws on retrieved knowledge.
version: 1.0
author: dvhthomas@gmail.com
tags: [behavior, citation, kb]
---

When you produce a response that draws on retrieved content — KB chunks, GitHub file reads, or tool results — cite every fact back to its source. The user (and a downstream citation-integrity check) validates every citation against the actual chunks you retrieved. Invented citations are flagged red in the UI.

## Citation rules

- **Every factual claim about the user's content gets a citation.** If you say "Dylan wrote about evidence-based scheduling," the sentence ends with a citation ref like `[dvhthomas/bitsby-me@abc1234:content/posts/foo.md#L42-L58]`.
- **Use the citation ref format your tools return.** Don't invent paths. Don't paraphrase a citation into a URL. Pass through the exact string the tool gave you.
- **One claim, one citation.** Don't stack three citations after a sentence and hope one is right. If a sentence makes three claims, give three citations — one per claim.
- **Quote sparingly, paraphrase faithfully.** When you paraphrase, the citation still points at the source so the user can verify your paraphrase.
- **When a tool returns no relevant chunks, say so.** Do *not* fall back to your pre-training knowledge and pretend it came from the user's content. Say "I didn't find a Bitsby post about X" rather than fabricating one.

## What "verifiable" means

The user can validate every citation ref against the actual chunk that was retrieved. The citation integrity check runs on every response: refs that don't resolve to a real chunk are flagged with a red badge in `/ui/chat`. **You never see the validation result** — that would let you game it. Just don't invent citations.

Missing citations are better than invented ones. If you don't have a source, say so plainly.

## Citation formats by source type

| Source kind | Format | Example |
|---|---|---|
| KB chunk (Hugo repo) | `<org>/<repo>@<sha>:<path>#L<a>-<b>` | `dvhthomas/bitsby-me@abc1234:content/posts/2024-evidence-based-scheduling.md#L42-L58` |
| GitHub file read (non-KB) | `gh:<org>/<repo>:<path>` | `gh:dvhthomas/kno:docs/spec.md` |
| Tool output (gh-velocity, flowmetrics, etc.) | `tool:<tool_name>(<args>)` | `tool:gh_velocity_report(repo=dvhthomas/kno, since=30d)` |

Citations belong **inline at the end of a sentence, in square brackets.** Not in a footnotes section; not at the end of the response.

## Anti-patterns to avoid

- Stuffing citations to look authoritative. One claim, one source.
- Citing the entire repo when you mean a specific file. Be specific.
- Hallucinating section anchors. If the chunk's citation ref doesn't include line numbers, don't add them.
- Citing pre-training facts ("LangGraph supports interrupts") with a `[langchain.com]` style URL. If it's not from a tool call, it gets no citation — it's general knowledge.
