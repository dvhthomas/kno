# AGENTS.md — project rules for AI coding assistants

> This file is the cross-tool convention for AI coding assistants (Claude Code, Codex, Cursor, etc.). `CLAUDE.md` is a symlink to this file. It is read on every session in this repo and encodes the **project's** durable rules. Personal/session-level notes live in tool-specific local memory and are separate.

---

## Strict TDD: red → green → refactor

**For every production code change in this repo, follow strict TDD in the order red → green → refactor. Evidence of the red phase must appear in the conversation before any production code is written. Failure to comply is grounds for immediate rejection of the change.**

The cycle:

1. **Red.** Before writing any production code, write a test that captures the gap — a feature not yet implemented, or a bug reproduced.
2. **Show the red.** Run the test. Paste the actual failure output (assertion error, traceback, missing-import, etc.) into the conversation. "Trust me, the test fails" is not sufficient — the failure must be demonstrated.
3. **Green.** Write the smallest production change that turns the test green. Re-run the test. Show the green output.
4. **Refactor.** Only after green, refactor for clarity or structure. Re-run tests to prove no regression. Show green again.
5. **Loop.** One test per cycle. Never bundle multiple features into one red-green pass.

### What this rules out

- Writing production code first and tests as coverage after.
- Skipping the red demonstration ("here's the test I would have written, here's the code").
- Bulk-implementing many features then making many tests pass at once.
- Refactoring while tests are red.

### Where this applies

- All Python production code under `src/kno/...`.
- Bug fixes anywhere.
- Migration code where behavior can be tested.

### Where this does NOT apply

- Pure config files: `pyproject.toml`, `alembic.ini`, `fly.toml`, `.pre-commit-config.yaml`, `Makefile`.
- Documentation: `docs/...`, `README.md`, `LICENSE`, ADRs.
- Seed data: `data.seed/...` (skills, workflow YAMLs, persona markdown).
- Project skeleton creation (Task 0.1 in `docs/tasks.md`) — that step creates the test harness itself; prerequisite to TDD, not subject to it.

### Edge case: refactoring without behavior change

If you want to refactor existing code without changing behavior, the existing tests must already cover that behavior. If they don't, **write the missing test first** (it should pass against the current implementation), and only then refactor. Strictly: writing a test-that-passes-now is permitted *only as a prerequisite to refactoring*, never as a substitute for the red phase of a new feature.

---

## Other project rules

(Add additional rules below as they emerge. Examples of the shape they'd take:)

- Browser is canonical for chat + setup + approval — see ADR-0018, ADR-0019. Don't propose CLI alternatives without a concrete trigger.
- v1 scope is **Kno-Lite** per ADR-0018. Don't propose adding deferred (v2) features to v1 unless the owner explicitly re-scopes.
- Cost-aware: per-session $0.50 cap; favor prompt caching + cheaper-model routing over re-prompting.

---

## Where to find things

| Looking for | File |
|---|---|
| What is Kno? Where do I start? | `README.md` |
| Full design spec (v0.9, Kno-Lite scope) | `docs/spec.md` |
| Build plan (3 phases) | `docs/plan.md` |
| Task list with acceptance criteria | `docs/tasks.md` |
| Architecture decisions | `docs/adr/` |
| Open-question research | `docs/notes/` |
| Local setup (running Kno on a laptop) | `docs/notes/setup/local-quickstart.md` |
| Backup / restore / wipe / export / key rotation | `docs/notes/data-management.md` |
| Platform / deploy / operate | `docs/ops.md` |
