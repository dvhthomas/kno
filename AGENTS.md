# AGENTS.md

## Strict TDD: red → green → refactor

**For every production code change in this repo, follow strict TDD per `/agent-skills:test`. Evidence of the red phase must appear in the conversation before any production code is written. Failure to comply is grounds for immediate rejection of the change.**

The cycle in brief — see `/agent-skills:test` for the full discipline:

1. **Red.** Write a failing test first.
2. **Show the red.** Paste actual failure output; "trust me, the test fails" is not sufficient.
3. **Green.** Smallest production change to pass.
4. **Refactor.** Only after green; re-run tests to confirm no regression.
5. **Loop.** One test per cycle.

### What this rules out

- Writing production code first and tests as coverage after.
- Skipping the red demonstration ("here's the test I would have written, here's the code").
- Bulk-implementing many features then making many tests pass at once.
- Refactoring while tests are red.

## See also

- [`docs/notes/dev-flow.md`](docs/notes/dev-flow.md) — branching, labels, PR template, how to query flow data for this repo (via `flowmetrics`, eventually the Flow Coach workflow).
- [`docs/spec.md`](docs/spec.md) — full design, v1 scope per ADR-0018.
- [`docs/plan.md`](docs/plan.md) / [`docs/tasks.md`](docs/tasks.md) — build plan + task list.
