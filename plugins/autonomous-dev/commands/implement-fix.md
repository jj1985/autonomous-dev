---
name: implement-fix
description: Minimal pipeline for test-fixing tasks
version: 1.0.0
user-invocable: false
---

# FIX MODE

> The key words "MUST", "MUST NOT", "SHOULD", and "MAY" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

Minimal pipeline (4 steps, 3 agents minimum) for test-fixing tasks.
Invoked via `/implement --fix "description"`. Skips research and planning
since the problem is already known (failing tests).

## Implementation

### STEP F1: Validate PROJECT.md Alignment

Read `.claude/PROJECT.md`. If missing: BLOCK ("Run `/setup` or `/align --retrofit`").
Check that the fix is within project scope. If misaligned: BLOCK with reason.

This is the same alignment gate as the full pipeline STEP 1.

### STEP F2: Gather Test Context

Run the test suite to capture current failures:

```bash
pytest --tb=short -q 2>&1 | head -200
```

Parse the output to identify:
- Number of passing vs failing tests
- Names of failing tests
- Affected source files (from traceback paths)
- Error messages and assertion failures

If ALL tests pass (0 failures): EXIT EARLY with message "All tests pass. No fix needed."

Display:
```
Fix Mode - Test Context:
  Failing tests: N
  Affected files: [list]
  Error summary: [brief]
```

### STEP F3: Implementer (Opus) - HARD GATE

Invoke the implementer agent with the failing test output and affected files.

```
subagent_type: "implementer"
model: "opus"
prompt: "FIX MODE: Fix failing tests. Do NOT add new features.

**Failing test output**:
[paste pytest output from STEP F2]

**Affected files**:
[list of files from traceback]

**Instructions**:
1. Read each failing test to understand what it expects
2. Read the source files being tested
3. Fix the source code to make tests pass (prefer fixing code over fixing tests)
4. If a test expectation is genuinely wrong, fix the test with a comment explaining why
5. Run pytest after each fix to verify progress

HARD GATE: ALL tests must pass (0 failures). Do not stop until pytest shows 0 failures."
```

**HARD GATE**: After implementer completes, run `pytest --tb=short -q` again.
If ANY test still fails: RE-INVOKE implementer with remaining failures.
Maximum 3 re-invocations before escalating to user.

### HARD GATE: Regression Test Requirement

If fixing a bug, at least one NEW test must be added that would FAIL without the fix. This ensures the bug never returns.

**Verification**: Compare test count from STEP F2 (before fix) vs after STEP F3 (after fix). If `after_count <= before_count`, BLOCK with message: "Bug fix requires at least one new regression test that reproduces the bug. Add a test that fails without your fix and passes with it."

**Exception**: If the bug was caught BY an existing failing test (i.e., the test that originally failed IS the regression test), this gate passes automatically. Document which existing test covers the regression.

**FORBIDDEN**:
- Fixing a bug without a test that proves it was broken
- Claiming "the fix is obvious and doesn't need a test"
- Adding a test that passes both with and without the fix (that's not a regression test)

### STEP F4: Reviewer + Doc-master (parallel)

Invoke TWO agents in PARALLEL:

1. **Reviewer** (Sonnet): Review the fix for correctness, edge cases, and regressions.

```
subagent_type: "reviewer"
model: "sonnet"
prompt: "Review this test fix for correctness and potential regressions.
[paste implementer output]
Focus on: correctness of fix, edge cases, potential regressions introduced."
```

2. **Doc-master** (Sonnet): Update any affected documentation.

```
subagent_type: "doc-master"
model: "sonnet"
prompt: "Check if any documentation needs updating based on this fix.
[paste implementer output]
Only update docs if behavior changed. Skip if fix is purely internal."
```

**Security-auditor**: SKIP unless changed files touch security-sensitive paths
(auth/, security/, crypto/, permissions/, .env, secrets, tokens).

---

## Agent Count

- **Minimum**: 3 agents (implementer, reviewer, doc-master)
- **Maximum**: 4 agents (+ security-auditor if security-sensitive files changed)

## Mutual Exclusivity

`--fix` is mutually exclusive with:
- `--batch` (batch file mode)
- `--issues` (batch issues mode)
- `--resume` (resume mode)

If combined with any of these, BLOCK with error message.
