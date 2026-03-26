---
name: implement-fix
description: Minimal pipeline for test-fixing tasks
version: 1.0.0
user-invocable: false
allowed-tools: [Agent, Read, Write, Edit, Bash, Grep, Glob, WebSearch, WebFetch]
---

# FIX MODE

> The key words "MUST", "MUST NOT", "SHOULD", and "MAY" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

Minimal pipeline (4 steps, 3 agents minimum) for test-fixing tasks.
Invoked via `/implement --fix "description"`. Skips research and planning
since the problem is already known (failing tests).

## Fix Mode Progress Protocol

Output structured progress at each step. Same format conventions as the full pipeline protocol.

**Step Banner**: `STEP FN/4 — Step Name` with agent info where applicable.
**Timing**: Capture `FIX_START=$(date +%s)` at pipeline start. Capture per-step timing.
**Gate Results**: `GATE: name — PASS/BLOCKED`
**Final Summary** (after STEP F4):
```
========================================
FIX COMPLETE
========================================
Step  Description         Agent(s)              Time    Status
----  ------------------  --------------------  ------  ------
F1    Alignment           —                     2s      PASS
F1.5  Pre-staged check    —                     1s      PASS
F2    Test context         —                    5s      done
F3    Implementation      implementer (Opus)    2:30    done
F3    Test gate           —                     8s      PASS
F4    Review + docs       reviewer, doc-master  45s     done
========================================
Total: 3:31 | Tests: N passed, M failed | Files changed: N
========================================
```

## Implementation

### STEP F1: Validate PROJECT.md Alignment

**Progress**: Output step banner (STEP F1/4 — Alignment). Capture FIX_START. Output gate result.

Read `.claude/PROJECT.md`. If missing: BLOCK ("Run `/setup` or `/align --retrofit`").
Check that the fix is within project scope. If misaligned: BLOCK with reason.

This is the same alignment gate as the full pipeline STEP 1.

### STEP F1.5: Pre-Staged Files Check — HARD GATE

**Progress**: Output step banner (STEP F1.5/4 — Pre-Staged Check). Output gate result.

```bash
STAGED_FILES=$(git diff --cached --name-only 2>/dev/null)
if [ -n "$STAGED_FILES" ]; then
  echo "BLOCKED: Pre-staged files detected"
  echo "$STAGED_FILES"
fi
```

If `STAGED_FILES` is non-empty: **BLOCK** the pipeline. Display:

```
BLOCKED — Pre-staged files detected.

The following files are already staged from a previous session:
[list files]

These would be bundled into this fix's commit, creating misleading git history.

Options:
A) Unstage: git reset HEAD
B) Commit first: git commit -m "wip: staged changes from previous session"
C) Review: git diff --cached
```

Do NOT proceed to STEP F2 until the staging area is clean.

**FORBIDDEN**:
- ❌ Proceeding with pre-staged files present
- ❌ Silently unstaging files without user confirmation
- ❌ Treating pre-staged files as part of the current fix

### STEP F2: Gather Test Context

**Progress**: Output step banner (STEP F2/4 — Test Context). Output test failure summary after.

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

**Progress**: Output step banner (STEP F3/4 — Implementation, Agent: implementer (Opus)). Output agent completion, then test gate result with counts.

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

**Progress**: Output step banner (STEP F4/4 — Review + Docs, Agents: reviewer (Sonnet), doc-master (Sonnet)). Output each agent completion. Then output Final Summary table.

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
