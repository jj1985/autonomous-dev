---
covers:
  - plugins/autonomous-dev/hooks/
  - plugins/autonomous-dev/lib/hook_exit_codes.py
---

# ADR-001: Agent Hooks for Quality Verification

**Status**: Accepted
**Date**: 2026-03-17
**Issue**: #467

---

## Context

All 17 active hooks in autonomous-dev use `type: command` — Python scripts that execute deterministically and return exit codes. Claude Code also supports `type: agent` hooks, which spawn a read-only subagent with:

- **50 tool turns** maximum
- **60-second timeout**
- **Read-only tools only**: Read, Grep, Glob (no Bash, Write, Edit)
- **Markdown prompt** (not Python script)
- **LLM-powered reasoning** over codebase contents

Agent hooks can perform semantic analysis that is impossible in pure Python — for example, checking whether test files actually test the corresponding source files, or whether docstrings match function behavior.

However, agent hooks introduce **LLM non-determinism**: the same codebase state may produce different results on different runs. This conflicts with the project's core philosophy of "hard blocking > nudges" (see MEMORY.md).

---

## Decision

Use agent hooks for **advisory-only** purposes on **non-blocking events** (Stop, PostToolUse). **Never** use agent hooks for enforcement or blocking decisions.

### Rules

1. Agent hooks MUST always return `{"decision": "approve"}` — never block.
2. Agent hooks MUST only use read-only tools (Read, Grep, Glob).
3. Agent hooks MUST only be registered on non-blocking events: `Stop`, `PostToolUse`.
4. Agent hooks MUST NOT be registered on blocking events: `PreCommit`, `PreToolUse`, `UserPromptSubmit`.
5. Agent hooks are **opt-in** — disabled by default in settings templates.

---

## Rationale

### Why advisory-only

The project's enforcement philosophy requires deterministic, repeatable results. A Python hook that checks "does file X exist?" always returns the same answer. An agent hook that evaluates "is this test adequate?" may say yes on one run and no on the next. Using non-deterministic hooks for blocking decisions would:

- Create flaky enforcement (sometimes blocks, sometimes doesn't)
- Erode trust in the pipeline ("it blocked me yesterday for the same code")
- Violate the "hard blocking > nudges" principle

### Why non-blocking events only

- `Stop` and `PostToolUse` already cannot block (exit code 2 is ignored)
- Advisory output on these events adds information without disrupting workflow
- Token cost is bounded by the 60-second timeout

### Why agent hooks at all

Some quality checks are **impossible in Python**:

- "Does this test file actually test the functions in the source file?"
- "Does the docstring match what the function does?"
- "Is this error message helpful enough?"

These require semantic understanding that only an LLM can provide. Advisory agent hooks fill this gap without compromising enforcement reliability.

---

## Consequences

### Positive

- Enables semantic quality checks impossible in Python hooks
- Advisory output helps developers catch issues early
- No risk to enforcement pipeline (always approves)
- Opt-in design means zero cost when disabled

### Negative

- Token cost per invocation (subagent uses model calls)
- Inconsistent advice across runs (LLM non-determinism)
- May produce false positives that developers learn to ignore
- Additional complexity in hook ecosystem

---

## Alternatives Considered

### (A) Agent hooks for enforcement (Rejected)

Use agent hooks with `{"decision": "block"}` on PreCommit events. Rejected because LLM non-determinism makes blocking unreliable. A hook that blocks 80% of the time is worse than one that blocks 100% or 0% of the time.

### (C) No agent hooks at all (Valid fallback)

Continue using only `type: command` Python hooks. This is the safe default and remains the fallback if agent hooks prove too noisy or expensive. The advisory-only approach can be abandoned at any time with no impact on enforcement.

---

## Configuration

Agent hooks are opt-in. To enable, add to `.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "type": "agent",
        "prompt": "plugins/autonomous-dev/hooks/Stop-verify-test-coverage.md",
        "description": "Advisory: check test coverage for modified files"
      }
    ]
  }
}
```

To disable, remove the entry from the `Stop` array. No environment variable needed — presence in settings.json controls activation.

---

## References

- [HOOKS.md](HOOKS.md) — Hook reference documentation
- [MEMORY.md](../.claude/projects/-Users-akaszubski-Dev-autonomous-dev/memory/MEMORY.md) — "Hard blocking > nudges" philosophy
- Claude Code hooks documentation — type:agent specification
