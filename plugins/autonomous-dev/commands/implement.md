---
name: implement
description: "Smart code implementation with full pipeline and batch modes"
argument-hint: "<feature> | --batch <file> | --issues <nums> | --resume <id>"
allowed-tools: [Agent, Read, Write, Edit, Bash, Grep, Glob, WebSearch, WebFetch]
---

# /implement — Thin Coordinator (Issue #444)

**You (Claude) are the coordinator.** Delegate specialist work to agents via the Agent tool. Each agent runs in isolated context — pass outputs from prior stages explicitly.

| Mode | Flag | Description |
|------|------|-------------|
| **Full Pipeline** | (default) | Acceptance-first: Research → Plan → Acceptance Tests → Implement + Unit Tests → Review → Security → Docs |
| **TDD-First** | `--tdd-first` | Research → Plan → Unit Tests → Implement → Review → Security → Docs |
| **Batch File** | `--batch <file>` | Process features from file with auto-worktree |
| **Batch Issues** | `--issues <nums>` | Process GitHub issues with auto-worktree |
| **Resume** | `--resume <id>` | Resume interrupted batch from checkpoint |

## Implementation

**COORDINATOR FORBIDDEN LIST** (violations = pipeline failure):
- ❌ Skipping any STEP (even under context pressure or time constraints)
- ❌ Summarizing agent output instead of passing full results to next agent
- ❌ Declaring "good enough" on failing tests (STEP 5 HARD GATE is absolute)
- ❌ Running STEP 6 before STEP 5 test gate passes
- ❌ Combining or parallelizing sequential steps (e.g., implementer + reviewer)
- ❌ Treating STEP 8 as the final step (STEP 9 is mandatory)
- ❌ Cleaning up pipeline state before STEP 9 launches
- ❌ Writing implementation code yourself instead of delegating to agents
- ❌ Containing detailed agent instructions inline — those belong in agents/*.md

ARGUMENTS: {{ARGUMENTS}}

---

### STEP 0: Parse Mode and Route

Parse ARGUMENTS: `--batch` → see [implement-batch.md](implement-batch.md), `--issues` → see [implement-batch.md](implement-batch.md), `--resume` → see [implement-resume.md](implement-resume.md), `--tdd-first` → FULL PIPELINE (TDD variant), `--acceptance-first` → recognized but no-op (same as default), else → FULL PIPELINE (acceptance-first default). Reject `--quick`. Auto-detect batch: 2+ issue refs → BATCH ISSUES MODE. Check `--no-cache` flag.

Activate pipeline state:
```bash
RUN_ID="$(date +%Y%m%d-%H%M%S)"
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

### STEP 1: Validate PROJECT.md Alignment — HARD GATE

Read `.claude/PROJECT.md`. If missing: BLOCK ("Run `/setup` or `/align --retrofit`"). Check feature against GOALS, SCOPE, CONSTRAINTS. If misaligned: BLOCK with reason and options.

### STEP 1.5: Check Research Cache

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

Invoke TWO agents in PARALLEL (single message, both Agent tool calls):
1. **Agent**(subagent_type="researcher-local", model="haiku") — "Search codebase for patterns related to: {feature}. Output JSON with findings and sources."
2. **Agent**(subagent_type="researcher", model="sonnet") — "Research best practices for: {feature}. MUST use WebSearch. Output JSON with findings, sources, security considerations."

Validation: If web researcher shows 0 tool uses, retry. Merge both outputs. Persist research via `save_merged_research()`.

### STEP 3: Planner (1 agent)

**Agent**(subagent_type="planner", model="opus") — Pass merged research + feature description. Output: file-by-file plan, dependencies, edge cases, testing strategy.

### STEP 3.5: Generate Acceptance Tests (default mode only)

Skip if `--tdd-first`. Check `tests/genai/conftest.py` exists (if not, fall back to TDD-first). Generate `tests/genai/test_acceptance_{slug}.py` with one `genai.judge()` test per acceptance criterion from planner output.

### STEP 4: Test-Master (--tdd-first only)

If `--tdd-first`: **Agent**(subagent_type="test-master", model="opus") — Pass planner output + file list + GenAI infra status (`test -f tests/genai/conftest.py && echo "GENAI_INFRA=EXISTS" || echo "GENAI_INFRA=ABSENT"`). Otherwise: skip (implementer writes unit tests alongside code in default acceptance-first mode).

### STEP 5: Implementer + Test Gate — HARD GATE

**Agent**(subagent_type="implementer", model="opus") — Pass planner output + acceptance tests (or test-master output if TDD). Must write WORKING code, no stubs.

**HARD GATE** (inline — coordinator must verify):
```bash
pytest --tb=short -q
```
For EACH failure, you MUST choose one:
1. **Fix it** — debug and fix code/test
2. **Adjust it** — update test expectations to match correct behavior

**HARD GATE: No New Skips** — Adding `@pytest.mark.skip` is FORBIDDEN. 0 new skips allowed. If a test fails, fix it or adjust expectations — never skip it.

Loop until **0 failures, 0 errors**. Do NOT proceed to STEP 6 with any failures.

Coverage check: `pytest tests/ --cov=plugins --cov-report=term-missing -q 2>&1 | tail -5` — must be >= baseline - 0.5%.

### STEP 5.5: Hook Registration Check — HARD GATE

If hooks were created/modified: verify they appear in `templates/settings.*.json`, `config/global_settings_template.json`, and `config/install_manifest.json`. BLOCK if unregistered.

### STEP 6: Parallel Validation (3 agents)

Invoke THREE agents in PARALLEL (single message):
1. **Agent**(subagent_type="reviewer", model="sonnet") — Pass file list + planner summary. Output: APPROVAL or issues.
2. **Agent**(subagent_type="security-auditor", model="sonnet") — Pass file list. Output: PASS/FAIL (OWASP Top 10).
3. **Agent**(subagent_type="doc-master", model="sonnet") — Pass file list + feature description. Update README, CHANGELOG, docstrings.

### STEP 7: Final Verification

Verify all required agents ran. Default: 7 (researcher-local, researcher, planner, implementer, reviewer, security-auditor, doc-master). TDD-first: 8 (add test-master). If any missing, invoke NOW.

### STEP 8: Report and Finalize

Report: 1-line per agent, files changed, tests, security PASS/FAIL, docs.

```bash
# Git push (if AUTO_GIT_PUSH=true)
git push origin $(git branch --show-current) 2>/dev/null || echo "Warning: Push failed"
# Close GitHub issue (if feature references #NNN)
COMMIT_SHA=$(git rev-parse --short HEAD)
gh issue close <number> -c "Implemented in $COMMIT_SHA" 2>/dev/null || echo "Warning: Could not close issue"
```

### STEP 8.5: Documentation Congruence — HARD GATE

```bash
pytest tests/unit/test_documentation_congruence.py --tb=short -q
```
If FAIL: invoke doc-master to fix, re-run until 0 failures. **FORBIDDEN**: skipping, proceeding with failures, manual edits without re-running tests.

### STEP 9: Continuous Improvement — HARD GATE

**REQUIRED**: **Agent**(subagent_type="continuous-improvement-analyst", model="sonnet", run_in_background=true) — Examines session logs for bypasses, test drift, pipeline completeness.

**FORBIDDEN** (violations = pipeline failure):
- ❌ Skipping STEP 9 for any reason (time pressure, context limits, "already reported")
- ❌ Cleaning up pipeline state before launching the analyst
- ❌ Inlining the analysis yourself instead of invoking the agent
- ❌ Treating STEP 8 as the final step — STEP 9 is mandatory

After launching analyst, cleanup: `rm -f /tmp/implement_pipeline_state.json && python3 -c "import sys; sys.path.insert(0, 'plugins/autonomous-dev/lib'); from pipeline_state import cleanup_pipeline; cleanup_pipeline('RUN_ID')" 2>/dev/null || true`

---

**Agents**: researcher-local (Haiku), researcher (Sonnet), planner (Opus), test-master (Opus, `--tdd-first` only), implementer (Opus), reviewer (Sonnet), security-auditor (Sonnet), doc-master (Sonnet), continuous-improvement-analyst (Sonnet). Default: 7 agents. TDD-first: 8 agents.

**Issue**: #203, #444 | **Version**: 3.48.0
