---
covers:
  - plugins/autonomous-dev/commands/implement.md
  - plugins/autonomous-dev/commands/implement-fix.md
  - plugins/autonomous-dev/commands/implement-batch.md
  - plugins/autonomous-dev/commands/implement-resume.md
---

# `/implement` Pipeline Modes

`/implement` runs different agent sets depending on the mode flag. This doc is the authoritative matrix — which agents run, in what order, and which gates fire.

## Mode Selection

| Mode | Flag | When to use |
|------|------|-------------|
| **Full (default)** | *(none)* — or `--tdd-first` | New features, bug fixes touching logic, anything security-sensitive |
| **Light** | `--light` | Markdown/config edits, docs, renames, typos — no new logic |
| **Fix** | `--fix` | Test failures, flaky tests, broken tests |
| **Batch (file)** | `--batch <file>` | Process a file of features with auto-worktree per feature |
| **Batch (issues)** | `--issues <nums>` | Process GitHub issues with auto-worktree per issue |
| **Resume** | `--resume <run_id>` | Recover from auto-compact / crash mid-pipeline |

**Auto-detection**: If no mode flag is given, `/implement` scans the feature description for signals:
- Fix keywords (`failing test`, `broken test`, `flaky test`) → suggests `--fix`
- Light keywords or file paths (`*.md`, `*.json`, `*.yaml`, docs-only) not matching security patterns → suggests `--light`
- Security-sensitive file (`hooks/*.py`, `lib/*security*`, `*.env*`, etc.) → forces full pipeline

## Agent Matrix

| Agent | Model | Full | `--tdd-first` | `--light` | `--fix` | `--batch` / `--issues` |
|-------|-------|------|---------------|-----------|---------|------------------------|
| researcher-local | haiku | ✓ | ✓ | ✗ | ✗ | ✓ per issue |
| researcher | sonnet | ✓ | ✓ | ✗ | ✗ | ✓ per issue |
| planner | opus / sonnet | ✓ | ✓ | ✓ (sonnet) | ✗ | ✓ per issue |
| plan-critic | opus | ✓ | ✓ | ✓ (1 round) | ✗ | ✓ per issue |
| test-master | opus | ✗ | ✓ | ✗ | ✗ | ✓ (TDD issues) |
| implementer | opus / sonnet | ✓ | ✓ | ✓ | ✓ | ✓ per issue |
| spec-validator | opus | ✓ | ✓ | ✓ | ✗ | ✓ per issue |
| reviewer | sonnet | ✓ | ✓ | ✗ | ✓ (bundled with docs) | ✓ per issue |
| security-auditor | sonnet | ✓ | ✓ | ✗ | ✗ | ✓ per issue |
| doc-master | sonnet | ✓ | ✓ | ✓ | ✓ | ✓ per issue |
| continuous-improvement-analyst | sonnet | ✓ (bg) | ✓ (bg) | ✓ (bg) | ✓ (bg) | ✓ post-batch |

**Minimum agents per mode:**
- Full (default, acceptance-first): 8 — researcher-local, researcher, planner, plan-critic, implementer, spec-validator, reviewer, security-auditor, doc-master (+CI analyst bg)
- `--tdd-first`: 9 — adds test-master before implementer
- `--light`: 4 — planner, plan-critic, implementer, doc-master (+CI analyst bg)
- `--fix`: 4 — implementer, reviewer+docs bundled, CI analyst bg
- `--batch` / `--issues`: full pipeline per issue + 1 post-batch CI analyst

**Research skip** (full mode only): If the feature description names a specific file path AND a specific modification instruction AND does NOT reference security-sensitive files or keywords (hooks, auth, secrets, tokens, SSO, OAuth, etc.), STEP 4 (research) is skipped. Research is NEVER skipped when touching `hooks/*.py`, `lib/*security*`, `lib/*auth*`, `*.env*`, `config/auto_approve_policy.json`, or migrations.

## Step-by-Step Sequence (Full Pipeline)

```
STEP 1   Pre-staged files check ......... HARD GATE
STEP 2   PROJECT.md alignment ........... HARD GATE
STEP 3   Research cache check
STEP 3.5 Fully-specified detection (may skip STEP 4)
STEP 4   Research (researcher-local + researcher in parallel)
STEP 4.5 Research completeness critique (inline)
STEP 5   Planning (planner)
STEP 5.5 Plan validation gate (plan-critic + structural checks) HARD GATE
STEP 6   Acceptance tests generation
STEP 7   Test-master (--tdd-first only)
STEP 8   Implementation + test gate ..... HARD GATE (0 failures)
STEP 8.5 Spec-blind validation (spec-validator) HARD GATE
STEP 9   Hook registration check ........ HARD GATE
STEP 9.5 Agent count gate ............... HARD GATE
STEP 9.7 Conditional UI testing (ui-tester if HTML/TSX changed)
STEP 9.8 Conditional mobile testing (mobile-tester if Swift/Kotlin/Dart changed)
STEP 10  Validation (reviewer + security-auditor + doc-master)
         — parallel if no security-sensitive files
         — sequential (reviewer → security) if hooks/*.py or *auth* changed
STEP 11  Remediation gate (max 2 cycles) HARD GATE
STEP 11.5 Skill effectiveness gate (if skills/ modified)
STEP 12  Final verification + doc-drift gate HARD GATE
STEP 13  Git operations (commit, push if AUTO_GIT_PUSH=true)
STEP 14  Documentation congruence ....... HARD GATE
STEP 15  Continuous improvement (bg analyst)
```

## Light Pipeline Sequence

```
L0  Pre-staged files check HARD GATE
L1  PROJECT.md alignment HARD GATE
L2  Planning (planner, sonnet)
L2.5 Plan structural validation HARD GATE
L3  Implementation + test gate HARD GATE
L3.5 Spec-blind validation HARD GATE
L4  Documentation (doc-master)
L5  Report and finalize + CI analyst bg
```

## Fix Pipeline Sequence

```
F1  Alignment check
F2  Test context (read failing tests, locate fixtures)
F3  Fix implementation (implementer) — regression test REQUIRED
F4  Review + docs (bundled)
F5  CI analysis (bg)
```

The fix pipeline is minimal because the user is reacting to a known failure. It DOES enforce the regression test gate (any fix must add a test that would have caught the bug).

## Gate Types

**HARD GATE** = JSON `{"decision": "block"}` returned by a hook. Prompt-level instructions ("please run tests") produce unreliable compliance (see [LLM Agents Are Hypersensitive to Nudges, 2025]). Hard gates are deterministic and can't be argued around.

**Advisory** = Warning surfaced in output, not blocking.

Gates in order of appearance:
1. Pre-staged files (no in-flight staging area) — STEP 1 / L0
2. PROJECT.md alignment (scope + goals) — STEP 2 / L1
3. Plan structural validation (file paths, acceptance criteria, testing strategy) — STEP 5.5c / L2.5
4. Plan-critic verdict (composite ≥ 3.0 to PROCEED) — STEP 5.5b
5. Test gate (0 pytest failures) — STEP 8 / L3 / F3
6. Regression test gate (bug fixes must add a test) — STEP 8 / F3
7. Plan-implementation alignment (< 50% scope divergence) — STEP 8
8. Spec-blind validation verdict (PASS required) — STEP 8.5 / L3.5
9. Hook registration (if new hooks) — STEP 9
10. Agent count gate (minimum agents ran) — STEP 9.5
11. Remediation gate (validators APPROVE / PASS) — STEP 11
12. Skill effectiveness gate (delta > -0.10 if skills modified) — STEP 11.5
13. Doc-drift gate (doc-master PASS, no stale docs) — STEP 12
14. Documentation congruence (counts match reality) — STEP 14

## How to Resume

If the pipeline is interrupted (auto-compact, crash, user `/clear`):

```bash
/implement --resume <run_id>
```

The `run_id` is printed at STEP 0. Pipeline state is at `/tmp/implement_pipeline_state.json` (per-session) and `~/.claude/pipeline_state/{run_id}.json` (persistent). `SessionStart-batch-recovery.sh` auto-restores batch state after `/clear` or auto-compact.

## Related

- [commands/implement.md](../plugins/autonomous-dev/commands/implement.md) — authoritative pipeline definition
- [AGENTS.md](AGENTS.md) — agent specs and model tiers
- [HOOKS.md](HOOKS.md) — which hooks enforce which gates
- [BATCH-PROCESSING.md](BATCH-PROCESSING.md) — batch mode deep-dive
- [WORKFLOW-DISCIPLINE.md](WORKFLOW-DISCIPLINE.md) — why hard gates over nudges
- [EVALUATION.md](EVALUATION.md) — how the CI analyst observes pipeline integrity
