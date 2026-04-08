# Terminal-Bench 2.0 Gap Analysis

**Date**: 2026-04-08
**Source**: terminal-bench 2.0 public leaderboard
**Purpose**: Identify architecture patterns that explain the 23.8pp gap between autonomous-dev's Claude Code baseline and top-performing agents, and prioritize improvements.

---

## TL;DR

Claude Code scores 58% on terminal-bench 2.0. ForgeCode running the same model (Claude Opus 4.6) scores 81.8%. The 23.8 percentage point gap is **entirely agent architecture** — same model, same compute, different harness. This document catalogs what the top agents do differently and maps each pattern to autonomous-dev's current state.

---

## Leaderboard (Top 10)

| Rank | Agent | Model | Score |
|------|-------|-------|-------|
| 1 | ForgeCode | GPT-5.4 | 81.8% |
| 2 | ForgeCode | Claude Opus 4.6 | 81.8% |
| 3 | TongAgents | Gemini 3.1 Pro | 80.2% |
| 4 | SageAgent | GPT-5.3-Codex | 78.4% |
| 5 | ForgeCode | Gemini 3.1 Pro | 78.4% |
| 6 | Droid | GPT-5.3-Codex | 77.3% |
| 7 | Capy | Claude Opus 4.6 | 75.3% |
| 8 | Simple Codex | GPT-5.3-Codex | 75.1% |
| 9 | Terminus-KIRA | Gemini 3.1 Pro | 74.8% |
| 10 | Terminus-KIRA | Claude Opus 4.6 | 74.7% |

**Baseline: Claude Code (unaugmented) = 58%**

Key observation: ForgeCode achieves identical scores (81.8%) on GPT-5.4 and Claude Opus 4.6. This means the architecture is doing the heavy lifting, not raw model capability.

---

## Per-Agent Architecture Analysis

### ForgeCode (25% → 81.8%)

ForgeCode published a breakdown of their 56.8pp improvement over baseline. The gains came in two phases:

**Phase 1 — 7 Foundational Fixes (25% → ~65%)**:
1. Non-interactive mode enforcement — all commands run with `-y`, `--yes`, `DEBIAN_FRONTEND=noninteractive`, and similar flags injected automatically
2. Tool-call naming consistency — unified tool names across model providers, eliminating provider-specific discrepancies
3. Planning enforcement — model cannot proceed to execution without a written plan; tool call blocked programmatically until plan is output
4. Skill/domain routing — task classifier routes to specialist sub-agents based on detected domain (filesystem, network, compilation, etc.)
5. Reasoning budget control — per-task token budgets with hard limits on exploration before commitment
6. (Undisclosed — possibly output format normalization)
7. (Undisclosed — possibly environment reset between subtasks)

**Phase 2 — 4 Refinement Fixes (~65% → 81.8%)**:
1. Required fields before `properties` in JSON schemas — prevented schema validation failures on tool calls
2. Schema flattening — removed nested `$defs` that some models couldn't resolve
3. Explicit truncation warnings — injected visible `[TRUNCATED: N bytes omitted]` markers so the model knows output was cut
4. Programmatic verification checklist — post-execution checklist: file exists, permissions correct, process running, output matches spec

**Multi-agent structure**:
- `muse`: analysis and decomposition (reads the task, produces structured plan)
- `forge`: execution (follows plan, calls tools)
- `sage`: review and verification (checks evidence that task is complete)

**Key quote** from ForgeCode's writeup: *"Opus reads between the lines. GPT reads the lines."* — their model-specific compensation accounts for Claude's tendency to infer intent rather than follow instructions literally.

---

### Terminus-KIRA (68.5% → 74.8%)

KIRA's 6.3pp gain came from six targeted additions:

1. **Smart completion verification** — instead of asking "is it done?", KIRA builds an evidence checklist at plan time and checks each item post-execution (file hash, process PID, port open, etc.)
2. **Non-interactive constraint** — not just a prompt instruction; tool wrapper rejects any command that requires stdin input, forcing the model to reformulate
3. **Pull-based execution polling** — instead of fire-and-forget shell commands, KIRA polls for marker files/signals to confirm asynchronous operations completed
4. **Adaptive replanning** — if execution hits unexpected output (unknown error code, missing dependency), triggers a mini-replan cycle rather than continuing blindly
5. **Image read tool** — specialized tool for reading screenshots and terminal renders, enabling multimodal verification
6. **Native tool calling** — bypassed string-parsed tool calls entirely, using the model provider's native function-calling API

---

### Meta-Harness (Stanford, 76.4%)

Source: https://yoonholee.com/meta-harness/

Meta-Harness takes a fundamentally different approach: instead of hand-engineering the harness, it **auto-discovers the optimal harness from execution traces**.

Key properties:
- Runs each benchmark task with multiple harness configurations
- Collects 10M tokens of diagnostic context across runs
- Uses trace-driven optimization — failures are analyzed to identify which harness property caused the failure
- Produces a task-specific harness per task category
- Insight: *Trace-driven optimization outperforms hand-engineered harnesses because it discovers failure modes humans don't anticipate.*

The 76.4% score is particularly notable because Meta-Harness uses GPT-4o-mini (not a frontier model), suggesting the harness quality gain exceeds the model capability gap.

---

### Capy (75.3%)

Capy focuses on parallelism and clean role separation:

- **Captain/Build agent separation** — Captain agent handles planning, orchestration, and decision-making; Build agent handles pure execution without needing task context
- **Parallel-first architecture** — independent subtasks are executed in parallel by default; Captain only serializes when it detects data dependency
- **No shared state between subtasks** — each Build invocation receives a clean environment, preventing cross-contamination

The separation means Captain can reason about the task without being distracted by execution details, and Build can execute without reasoning overhead.

---

## Convergent Patterns

Across all top-10 agents, six patterns appear universally:

| # | Pattern | Description |
|---|---------|-------------|
| 1 | **Planning enforced programmatically** | Tool calls blocked until a structured plan is output. Not a prompt instruction — a hard gate. |
| 2 | **Mandatory completion verification** | Post-execution evidence check. Not "did the command succeed?" but "does the filesystem/process/output prove it worked?" |
| 3 | **Non-interactive constraint explicit** | Commands that require stdin input are rejected at the tool layer, not corrected via prompt. |
| 4 | **Truncation handling visible to model** | When output is truncated, a visible `[TRUNCATED]` marker is injected. The model knows it has incomplete information. |
| 5 | **Analysis separated from execution** | The agent that reasons about the task is structurally separate from the agent that executes it. No context bleed between analysis and execution. |
| 6 | **Model-specific failure mode compensation** | Prompts and constraints are tuned per model. Claude gets different instructions than GPT. |

---

## Gap Analysis: autonomous-dev vs Convergent Patterns

| Convergent Pattern | autonomous-dev Status | Mechanism / Files | Gap Severity |
|---|---|---|---|
| Planning enforcement | **HAS** | `implement.md` STEP 5 mandatory, hooks block skip | Low |
| Completion verification | **PARTIAL** | reviewer + test gate, but no evidence checklist | Medium |
| Non-interactive constraint | **N/A** | autonomous-dev is interactive CLI, not benchmark runner | None |
| Truncation handling | **PARTIAL** | context budget in `PROJECT.md`, no inline `[TRUNCATED]` warnings | Medium |
| Analysis/execution separation | **HAS** | planner (Opus) + implementer (Opus) are separate agent invocations | Low |
| Model-specific compensation | **MISSING** | Same prompts for all models, no per-model tuning | High |
| Skill/tool routing | **HAS** | Skills frontmatter + progressive disclosure per pipeline step | Low |
| Completion checklist | **PARTIAL** | Test gate + anti-stubbing HARD GATE, but checklist is code-oriented, not evidence-based | Medium |

### Severity Definitions

- **Low**: Gap exists but autonomous-dev has a functional equivalent. Minor improvement opportunity.
- **Medium**: Gap affects output quality measurably. Improvement would reduce review cycles.
- **High**: Gap has no equivalent in autonomous-dev. Improvement would be additive capability.

---

## What autonomous-dev Already Does Well

The analysis confirms several areas where autonomous-dev matches or exceeds top-agent patterns:

1. **Planning enforcement** — STEP 5 in `implement.md` is mandatory with hooks that block skip. Equivalent to ForgeCode's Phase 1 fix #3.

2. **Agent separation** — 14 specialists with fresh context per invocation. Planner and implementer are structurally separate. Equivalent to ForgeCode's muse/forge separation and Capy's captain/build split.

3. **Skill routing** — Progressive skills injection based on pipeline step. Domain-appropriate context is injected without bloating unrelated steps. Equivalent to ForgeCode's Phase 1 fix #4.

4. **Error recovery** — Pipeline-native remediation loop (STEP 11 in `implement.md`). When reviewer or security-auditor fails, the pipeline enters a max-2-cycle remediation loop that re-invokes only the failing validators after fixes, rather than retrying the entire pipeline. This exceeds what most benchmark agents do (they typically retry rather than selectively re-validate).

5. **Output validation** — reviewer with minimum tool-use enforcement. The reviewer is required to actually check artifacts, not just read the implementation. Equivalent to ForgeCode's sage role.

---

## Prioritized Recommendations

The following improvements address the Medium and High severity gaps. Each has a corresponding GitHub issue filed.

1. **Evidence-based completion verification checklist for reviewer** (Medium gap, Issue #727)
   Reviewer currently checks code quality and test results. It does not verify filesystem artifacts, process state, or output signatures. Adding a structured evidence checklist (similar to KIRA's post-execution verification) would reduce false-positive completions.

2. **Model-specific prompt compensation for multi-model tiers** (High gap, Issue #728)
   autonomous-dev uses three model tiers (Haiku/Sonnet/Opus) but applies identical prompts to each. Top agents tune per-model. For Opus specifically, this means adding explicit "literal interpretation" guards. For Haiku, it means shorter, more directive prompts. This is the highest-severity gap.

3. **Inline truncation warnings when context approaches limits** (Medium gap, Issue #729)
   When pipeline context approaches the budget defined in `PROJECT.md`, the model currently receives no in-band signal. Injecting `[CONTEXT APPROACHING LIMIT: N tokens remaining]` warnings into the active agent's context would match ForgeCode's Phase 2 fix #3.

4. **Adaptive replanning when implementer encounters blocking information** (Medium gap, Issue #730)
   Implementer currently escalates to remediation when blocked. Remediation is a separate pipeline step with overhead. A lighter-weight adaptive replanning mechanism — triggered by detected blocking signals in tool output — would allow mid-execution course correction without full remediation overhead.

---

## Sources

- terminal-bench 2.0 public leaderboard: https://terminal-bench.github.io/leaderboard
- ForgeCode architecture writeup: https://forgecode.dev/blog/terminal-bench-breakdown
- Meta-Harness paper (Stanford): https://yoonholee.com/meta-harness/
- Terminus-KIRA release notes: https://terminus-ai.io/kira/changelog
- Capy architecture overview: https://capy.dev/docs/architecture
- terminal-bench benchmark definition: https://github.com/terminal-bench/terminal-bench
