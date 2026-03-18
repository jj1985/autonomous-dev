---
name: implement
description: "Smart code implementation with full pipeline and batch modes"
argument-hint: "<feature> | --batch <file> | --issues <nums> | --resume <id>"
allowed-tools: [Agent, Read, Write, Edit, Bash, Grep, Glob, WebSearch, WebFetch]
user-invocable: true
---

# /implement — Thin Coordinator (Issue #444)

> The key words "MUST", "MUST NOT", "SHOULD", and "MAY" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

**You (Claude) are the coordinator.** Delegate specialist work to agents via the Agent tool. Each agent runs in isolated context — pass outputs from prior stages explicitly.

| Mode | Flag | Description |
|------|------|-------------|
| **Full Pipeline** | (default) | Acceptance-first: Research → Plan → Acceptance Tests → Implement + Unit Tests → Review → Security → Docs |
| **Light** | `--light` | Fast pipeline: Align → Plan → Implement → Test → Docs (4 agents, no research/security/CI) |
| **TDD-First** | `--tdd-first` | Research → Plan → Unit Tests → Implement → Review → Security → Docs |
| **Fix** | `--fix` | Minimal pipeline: Align → Test Context → Implement Fix → Review + Docs (3 agents) |
| **Batch File** | `--batch <file>` | Process features from file with auto-worktree |
| **Batch Issues** | `--issues <nums>` | Process GitHub issues with auto-worktree |
| **Resume** | `--resume <id>` | Resume interrupted batch from checkpoint |

## Implementation

**COORDINATOR FORBIDDEN LIST** — You MUST NOT do any of the following (violations = pipeline failure):
- ❌ You MUST NOT skip any STEP (even under context pressure or time constraints)
- ❌ You MUST NOT summarize agent output instead of passing full results to next agent
- ❌ You MUST NOT declare "good enough" on failing tests (STEP 5 HARD GATE is absolute)
- ❌ You MUST NOT run STEP 6 before STEP 5 test gate passes
- ❌ You MUST NOT combine or parallelize sequential steps (e.g., implementer + reviewer)
- ❌ You MUST NOT treat STEP 8 as the final step (STEP 9 is mandatory)
- ❌ You MUST NOT clean up pipeline state before STEP 9 launches
- ❌ You MUST NOT write implementation code yourself instead of delegating to agents
- ❌ You MUST NOT contain detailed agent instructions inline — those belong in agents/*.md

### Pipeline Progress Protocol

**You MUST output structured progress to the user at each pipeline milestone.** This keeps the user informed of what's happening, which agents are running, and how long each step takes.

**Timing**: Capture `STEP_START=$(date +%s)` before each step. After each step, calculate elapsed: `STEP_ELAPSED=$(( $(date +%s) - STEP_START ))`. Format: `Xs` if under 60s, `M:SS` if 60s+.

**Step Banner** — output before each step begins:
```
========================================
STEP N/TOTAL — Step Name
Agent: agent-name (Model) [or "Agents: a, b (Model)" for parallel]
========================================
```

For non-agent steps (gates, checks), omit the Agent line.

**Agent Completion** — output after each agent returns:
```
  [done] agent-name              Xs
```
On failure:
```
  [FAIL] agent-name              Xs — reason
```

**HARD GATE Result** — output after each gate check:
```
  GATE: gate-name — PASS                Xs
```
or:
```
  GATE: gate-name — BLOCKED (reason)
```

**Test Gate Result** (STEP 5) — output after pytest:
```
  Tests: N passed, M failed, K skipped | Coverage: X.X% (baseline: Y.Y%)
```

**Final Summary** (STEP 8) — output the full pipeline summary:
```
========================================
PIPELINE COMPLETE
========================================
Step   Description                  Agent(s)                     Time     Status
-----  ---------------------------  ---------------------------  -------  ------
0.5    Pre-staged check             —                            2s       PASS
1      Alignment                    —                            3s       PASS
1.5    Research cache               —                            1s       MISS
2      Research                     researcher-local, researcher 45s      done
3      Planning                     planner                      1:32     done
3.5    Acceptance tests             —                            18s      done
5      Implementation               implementer                  3:45     done
5      Test gate                    —                            12s      PASS
5.5    Hook registration            —                            2s       PASS
6      Validation                   reviewer, security, docs     52s      done
7      Verification                 —                            3s       PASS
8      Git operations               —                            5s       done
8.5    Doc congruence               —                            8s       PASS
9      Continuous improvement       ci-analyst                   (bg)     done
========================================
Total: 7:08 | Files changed: N | Tests: N passed, M failed | Security: PASS
========================================
```

ARGUMENTS: {{ARGUMENTS}}

---

### STEP 0: Parse Mode and Route

Parse ARGUMENTS: `--batch` → see [implement-batch.md](implement-batch.md), `--issues` → see [implement-batch.md](implement-batch.md), `--resume` → see [implement-resume.md](implement-resume.md), `--fix` → see [implement-fix.md](implement-fix.md), `--light` → LIGHT PIPELINE MODE (below), `--tdd-first` → FULL PIPELINE (TDD variant), `--acceptance-first` → recognized but no-op (same as default), else → FULL PIPELINE (acceptance-first default). Reject `--quick`. Auto-detect batch: 2+ issue refs → BATCH ISSUES MODE. Check `--no-cache` flag.

**Mutual exclusivity**: `--fix` and `--light` are each mutually exclusive with `--batch`, `--issues`, and `--resume`. If combined, BLOCK with error. `--light` and `--fix` are also mutually exclusive.

**Auto-mode detection** — If no mode flag was explicitly provided (no `--fix`, `--light`, `--batch`, `--issues`, `--resume`, `--tdd-first` in ARGUMENTS), scan the feature description (case-insensitive) for signal patterns:

- **Fix signals**: "fix test", "failing test", "broken test", "test failure", "flaky test", "skip test" → candidate: `--fix`
- **Light signals**: "update docs", "update readme", "readme", "changelog", "typo", "rename", "config change", "update comment" → candidate: `--light`
- **Tie-break**: If both fix and light patterns match, suggest `--fix`.

If a candidate is detected, output and STOP — wait for user response before proceeding:

```
Auto-detected: This looks like a [test fix | docs/config change].
Recommended: --[fix|light] ([one-line description from mode table])
Full pipeline: Research → Plan → Acceptance Tests → Implement → Review → Security → Docs

Proceed with --[fix|light]? (reply "yes" to confirm, anything else runs the full pipeline)
```

- User confirms ("yes", "y", or repeats the mode name) → route to suggested mode
- Anything else → FULL PIPELINE (default)
- No pattern match → proceed directly to FULL PIPELINE without prompting

**FORBIDDEN**: ❌ Silently switching mode without user confirmation. ❌ Prompting when a mode flag was explicitly specified. ❌ Blocking pipeline on ambiguous reply — default to FULL PIPELINE.

Activate pipeline state:
```bash
RUN_ID="$(date +%Y%m%d-%H%M%S)"
PIPELINE_START=$(date +%s)
python3 -c "
import sys; sys.path.insert(0, 'plugins/autonomous-dev/lib')
from pipeline_state import create_pipeline, save_pipeline
state = create_pipeline('$RUN_ID', 'FEATURE_DESC', mode='MODE')
save_pipeline(state)
print(f'Pipeline {state.run_id} initialized')
"
echo '{"session_start":"'$(date +%Y-%m-%dT%H:%M:%S)'","mode":"MODE","run_id":"'$RUN_ID'"}' > /tmp/implement_pipeline_state.json
```

---

# FULL PIPELINE MODE (Default)

Execute steps IN ORDER. Default mode uses acceptance-first testing (7 agents). TDD-first mode (`--tdd-first`) adds test-master (8 agents).

### STEP 0.5: Pre-Staged Files Check — HARD GATE

**Progress**: Output step banner (STEP 1/14 — Pre-Staged Files Check). Output gate result after check.

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

These would be bundled into this feature's commit, creating misleading git history.

Options:
A) Unstage: git reset HEAD
B) Commit first: git commit -m "wip: staged changes from previous session"
C) Review: git diff --cached
```

Do NOT proceed to STEP 1 until the staging area is clean.

**FORBIDDEN**:
- ❌ Proceeding with pre-staged files present
- ❌ Silently unstaging files without user confirmation
- ❌ Treating pre-staged files as part of the current feature

### STEP 1: Validate PROJECT.md Alignment — HARD GATE

**Progress**: Output step banner (STEP 2/14 — Alignment). Output gate result after.

Read `.claude/PROJECT.md`. If missing: BLOCK ("Run `/setup` or `/align --retrofit`"). Check feature against GOALS, SCOPE, CONSTRAINTS. If misaligned: BLOCK with reason and options.

### STEP 1.5: Check Research Cache

**Progress**: Output step banner (STEP 3/14 — Research Cache). Output CACHE_HIT or CACHE_MISS after.

```bash
python3 -c "
import sys; sys.path.insert(0, 'plugins/autonomous-dev/lib')
from research_persistence import check_cache, load_cached_research
cached = check_cache('FEATURE_TOPIC', max_age_days=7)
print('CACHE_HIT' if cached else 'CACHE_MISS')
"
```
CACHE_HIT → load cached research, skip STEP 2, pass to STEP 3. CACHE_MISS → proceed to STEP 2.

### STEP 2: Parallel Research (2 agents)

**Progress**: Output step banner (STEP 4/14 — Research, Agents: researcher-local (Haiku), researcher (Sonnet)). Output agent completions after each returns.

Invoke TWO agents in PARALLEL (single message, both Agent tool calls):
1. **Agent**(subagent_type="researcher-local", model="haiku") — "Search codebase for patterns related to: {feature}. Output JSON with findings and sources."
2. **Agent**(subagent_type="researcher", model="sonnet") — "Research best practices for: {feature}. MUST use WebSearch. Output JSON with findings, sources, security considerations."

Validation: If web researcher shows 0 tool uses, retry. Merge both outputs. Persist research via `save_merged_research()`.

### STEP 3: Planner (1 agent)

**Progress**: Output step banner (STEP 5/14 — Planning, Agent: planner (Opus)). Output agent completion after.

**Agent**(subagent_type="planner", model="opus") — Pass merged research + feature description. Output: file-by-file plan, dependencies, edge cases, testing strategy.

### STEP 3.5: Generate Acceptance Tests (default mode only)

**Progress**: Output step banner (STEP 6/14 — Acceptance Tests). Output completion after.

Skip if `--tdd-first`. Check `tests/genai/conftest.py` exists (if not, fall back to TDD-first). Generate `tests/genai/test_acceptance_{slug}.py` with one `genai.judge()` test per acceptance criterion from planner output.

### STEP 4: Test-Master (--tdd-first only)

**Progress**: Output step banner (STEP 7/14 — Test-Master, Agent: test-master (Opus)). Skip banner if not --tdd-first. Output agent completion after.

If `--tdd-first`: **Agent**(subagent_type="test-master", model="opus") — Pass planner output + file list + GenAI infra status (`test -f tests/genai/conftest.py && echo "GENAI_INFRA=EXISTS" || echo "GENAI_INFRA=ABSENT"`). Otherwise: skip (implementer writes unit tests alongside code in default acceptance-first mode).

### STEP 5: Implementer + Test Gate — HARD GATE

**Progress**: Output step banner (STEP 8/14 — Implementation + Test Gate, Agent: implementer (Opus)). Output agent completion, then test gate result with pass/fail/skip counts and coverage after.

**Agent**(subagent_type="implementer", model=PLANNER_RECOMMENDED_MODEL) — Pass planner output + acceptance tests (or test-master output if TDD). Must write WORKING code, no stubs. Use the model recommended by the planner (see STEP 3). Default to "opus" if planner did not specify.

**HARD GATE** (inline — coordinator must verify):
```bash
pytest --tb=short -q
```
For EACH failure, you MUST choose one:
1. **Fix it** — debug and fix code/test
2. **Adjust it** — update test expectations to match correct behavior

**HARD GATE: No New Skips** — Adding `@pytest.mark.skip` is FORBIDDEN. 0 new skips allowed. Skip count is tracked across sessions via `coverage_baseline.check_skip_regression()`. If the current skip count exceeds the baseline, the quality gate BLOCKS.

**FORBIDDEN** — You MUST NOT do any of the following (coverage/skip violations):
- ❌ You MUST NOT add `@pytest.mark.skip` to any test (0 new skips, enforced by baseline comparison)
- ❌ You MUST NOT let coverage drop more than 0.5% below baseline (enforced by `coverage_baseline.check_coverage_regression()`)
- ❌ You MUST NOT declare coverage loss "acceptable" or "minor"
- ❌ You MUST NOT proceed to STEP 6 when `step5_quality_gate.run_quality_gate()` returns `passed=False`

Loop until **0 failures, 0 errors**. Do NOT proceed to STEP 6 with any failures.

Coverage check: `pytest tests/ --cov=plugins --cov-report=term-missing -q 2>&1 | tail -5` — must be >= baseline - 0.5%. On success, baseline is automatically updated via `coverage_baseline.save_baseline()`.

### STEP 5.5: Hook Registration Check — HARD GATE

**Progress**: Output step banner (STEP 9/14 — Hook Registration). Output gate result after.

If hooks were created/modified: verify they appear in `templates/settings.*.json`, `config/global_settings_template.json`, and `config/install_manifest.json`. BLOCK if unregistered.

### STEP 6: Parallel Validation (3 agents)

**Progress**: Output step banner (STEP 10/14 — Validation, Agents: reviewer (Sonnet), security-auditor (Sonnet), doc-master (Sonnet)). Output each agent completion as they return.

Invoke THREE agents in PARALLEL (single message):
1. **Agent**(subagent_type="reviewer", model="sonnet") — Pass file list + planner summary. Output: APPROVAL or issues.
2. **Agent**(subagent_type="security-auditor", model="sonnet") — Pass file list. Output: PASS/FAIL (OWASP Top 10).
3. **Agent**(subagent_type="doc-master", model="sonnet") — Pass file list + feature description. Update README, CHANGELOG, docstrings.

### STEP 7: Final Verification

**Progress**: Output step banner (STEP 11/14 — Final Verification). Output result after.

Verify all required agents ran. Default: 7 (researcher-local, researcher, planner, implementer, reviewer, security-auditor, doc-master). TDD-first: 8 (add test-master). If any missing, invoke NOW.

### STEP 8: Report and Finalize

**Progress**: Output the **Final Summary** table per Pipeline Progress Protocol. Include per-step elapsed times, total pipeline time (from PIPELINE_START), files changed, test counts, and security result. Then proceed with git operations.

```bash
# Git push (if AUTO_GIT_PUSH=true)
git push origin $(git branch --show-current) 2>/dev/null || echo "Warning: Push failed"
# Close GitHub issue (if feature references #NNN)
COMMIT_SHA=$(git rev-parse --short HEAD)
gh issue close <number> -c "Implemented in $COMMIT_SHA" 2>/dev/null || echo "Warning: Could not close issue"
```

### STEP 8.5: Documentation Congruence — HARD GATE

**Progress**: Output step banner (STEP 13/14 — Documentation Congruence). Output gate result after.

```bash
pytest tests/unit/test_documentation_congruence.py --tb=short -q
```
If FAIL: invoke doc-master to fix, re-run until 0 failures. **FORBIDDEN**: skipping, proceeding with failures, manual edits without re-running tests.

### STEP 9: Continuous Improvement — HARD GATE

**Progress**: Output step banner (STEP 14/14 — Continuous Improvement). Output agent launch confirmation.

**REQUIRED**: **Agent**(subagent_type="continuous-improvement-analyst", model="sonnet", run_in_background=true) — Examines session logs for bypasses, test drift, pipeline completeness.

**FORBIDDEN** — You MUST NOT do any of the following (violations = pipeline failure):
- ❌ You MUST NOT skip STEP 9 for any reason (time pressure, context limits, "already reported")
- ❌ You MUST NOT clean up pipeline state before launching the analyst
- ❌ You MUST NOT inline the analysis yourself instead of invoking the agent
- ❌ You MUST NOT treat STEP 8 as the final step — STEP 9 is mandatory

After launching analyst, cleanup: `rm -f /tmp/implement_pipeline_state.json && python3 -c "import sys; sys.path.insert(0, 'plugins/autonomous-dev/lib'); from pipeline_state import cleanup_pipeline; cleanup_pipeline('RUN_ID')" 2>/dev/null || true`

---

# LIGHT PIPELINE MODE (`--light`)

Fast pipeline for low-risk changes: markdown, config, docs, simple edits, renames. 5 steps, 4 agents. Skips research, acceptance tests, security audit, reviewer, CI analyst.

**When to use**: `--light` flag, or coordinator MAY suggest it when the feature description clearly involves only markdown/config/docs/typos/renames and no new logic or security-sensitive code.

**When NOT to use**: New features with logic, security-sensitive changes, API changes, hook/agent modifications that need security review.

### STEP L0: Pre-Staged Files Check — HARD GATE

Same as STEP 0.5 in full pipeline.

### STEP L1: Validate PROJECT.md Alignment — HARD GATE

**Progress**: Output step banner (STEP 1/5 — Alignment).

Same as STEP 1 in full pipeline.

### STEP L2: Planner (1 agent)

**Progress**: Output step banner (STEP 2/5 — Planning, Agent: planner (Sonnet)).

**Agent**(subagent_type="planner", model="sonnet") — Pass feature description. No research input (skipped). Output: file-by-file plan, testing strategy, and `Recommended implementer model: sonnet|opus`.

### STEP L3: Implementer + Test Gate — HARD GATE

**Progress**: Output step banner (STEP 3/5 — Implementation + Test Gate, Agent: implementer (PLANNER_RECOMMENDED_MODEL)).

**Agent**(subagent_type="implementer", model=PLANNER_RECOMMENDED_MODEL) — Pass planner output. Default to "sonnet" if planner did not specify. Must write WORKING code, no stubs.

**HARD GATE**: Same test gate as STEP 5 in full pipeline:
```bash
pytest --tb=short -q
```
Loop until **0 failures, 0 errors**.

Coverage check: `pytest tests/ --cov=plugins --cov-report=term-missing -q 2>&1 | tail -5` — must be >= baseline - 0.5%.

### STEP L4: Doc-master (1 agent)

**Progress**: Output step banner (STEP 4/5 — Documentation, Agent: doc-master (Sonnet)).

**Agent**(subagent_type="doc-master", model="sonnet") — Pass file list + feature description. Update CHANGELOG, docstrings, README if needed.

### STEP L5: Report and Finalize

**Progress**: Output Final Summary table (adapted for 5 steps).

```
========================================
LIGHT PIPELINE COMPLETE
========================================
Step  Description         Agent(s)              Time    Status
----  ------------------  --------------------  ------  ------
L0    Pre-staged check    —                     Xs      PASS
L1    Alignment           —                     Xs      PASS
L2    Planning            planner (Sonnet)      Xs      done
L3    Implementation      implementer (model)   Xs      done
L3    Test gate           —                     Xs      PASS
L4    Documentation       doc-master (Sonnet)   Xs      done
========================================
Total: Xs | Files changed: N | Tests: N passed, M failed
========================================
```

```bash
# Git push (if AUTO_GIT_PUSH=true)
git push origin $(git branch --show-current) 2>/dev/null || echo "Warning: Push failed"
```

Cleanup: `rm -f /tmp/implement_pipeline_state.json`

**Agents (light)**: planner (Sonnet), implementer (Sonnet or Opus per planner), doc-master (Sonnet). 3-4 agents.

---

**Agents (full)**: researcher-local (Haiku), researcher (Sonnet), planner (Opus), test-master (Opus, `--tdd-first` only), implementer (per planner recommendation, default Opus), reviewer (Sonnet), security-auditor (Sonnet), doc-master (Sonnet), continuous-improvement-analyst (Sonnet). Default: 7 agents. TDD-first: 8 agents.

**Issue**: #203, #444 | **Version**: 3.48.0
