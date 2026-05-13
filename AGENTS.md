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

**Before any draft PR is flipped to ready-for-review, the executing agent MUST invoke `Agent(subagent_type="agent-skills:code-reviewer")` against the PR's full diff vs. `main` at the moment of `gh pr ready`, post the findings as a PR comment, and address every Critical and Important finding. Skipping the invocation is grounds for immediate rejection.**

**Definition of "addressed":** either (a) a follow-up commit on the same branch that the code-reviewer subagent, on re-invocation, confirms resolves the finding, OR (b) an explicit `wontfix:` reply comment on the PR citing concretely why the finding does not apply.

Conditional triggers in addition to the above:

- PR touches auth / sessions / secrets / OAuth / user input parsing / new external API surface → ALSO invoke `Agent(subagent_type="agent-skills:security-auditor")`.
- PR adds, modifies, or restructures **test infrastructure** (fixtures, conftest.py, custom pytest plugins, test harness, mock factories) → ALSO invoke `Agent(subagent_type="agent-skills:test-engineer")`. *Per-feature TDD test additions are covered by the strict-TDD rule and do not separately require test-engineer.*

The subagent form (`Agent(subagent_type=…)`) is canonical for these gates — it isolates the review into its own context and returns a self-contained verdict. The `/agent-skills:review` slash command is for interactive human use, not for fulfilling the gate.

**Status: agent-discipline-enforced in Phase 1.** Issue [#11](https://github.com/dvhthomas/kno/issues/11) tracks the Phase 2 GitHub Action that will assert the presence of a properly-signed code-reviewer comment before allowing `ready_for_review`.

See [`docs/notes/dev-flow.md` → Subagent review gates](docs/notes/dev-flow.md#subagent-review-gates) for the full mapping plus the MAY-invoke menu of judgment-call helpers.

## Strict pre-deploy review

**Before any production deploy (`fly deploy` or equivalent), the executing agent MUST run `/agent-skills:ship` to fan out the pre-launch checklist and produce a go/no-go decision. A No-Go halts the deploy until the listed blockers are resolved.**

## See also

- [`docs/spec.md`](docs/spec.md) — full design, v1 scope per ADR-0018.
- [`docs/plan.md`](docs/plan.md) / [`docs/tasks.md`](docs/tasks.md) — build plan + task list.
