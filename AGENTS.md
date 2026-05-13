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

## Strict dev-flow compliance

**All work in this repo MUST follow [`docs/notes/dev-flow.md`](docs/notes/dev-flow.md): branch naming, PR-based flow, label and board mechanics, conventional commit prefixes, and the closing rule. Non-compliant changes will be rejected out of hand.**

## Strict pre-merge review

**Before `gh pr ready` on any draft PR, the executing agent MUST invoke `Agent(subagent_type="agent-skills:code-reviewer")` against the PR's full diff vs. `main`, post findings as a PR comment, and address every Critical and Important finding. Skipping = rejection.**

**Addressed** means either (a) a follow-up commit the subagent confirms resolves the finding on re-invocation, OR (b) an explicit `wontfix:` PR reply with concrete reasoning.

Additional invocations on top of code-reviewer:

- auth / sessions / secrets / OAuth / user input / external API surface → `agent-skills:security-auditor`
- test infrastructure (fixtures, `conftest.py`, harness) → `agent-skills:test-engineer`

Phase 1 (agent-discipline-enforced). [#11](https://github.com/dvhthomas/kno/issues/11) tracks the Phase 2 Action that will fail the check when the review comment is absent.

## Strict pre-deploy review

**Before `fly deploy` (or equivalent), the executing agent MUST run `/agent-skills:ship`. No-Go halts the deploy until the listed blockers are resolved.**

## See also

- [`docs/spec.md`](docs/spec.md) — full design, v1 scope per ADR-0018.
- [`docs/plan.md`](docs/plan.md) / [`docs/tasks.md`](docs/tasks.md) — build plan + task list.
