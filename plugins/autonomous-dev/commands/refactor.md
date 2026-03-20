---
name: refactor
description: "Unified code, docs, and test optimization -- shape analysis, waste detection, dead code, doc redundancy"
argument-hint: "[--tests] [--docs] [--code] [--fix] [--quick]"
user-invocable: true
---

# Refactor: Unified Code, Docs, and Test Optimization

Deep analysis and optimization of tests (Quality Diamond shape, waste detection), docs (redundancy), and code (dead code, unused libs). Supersedes `/sweep` with deeper analysis. Use `--quick` for the original sweep-style hygiene check.

## Implementation

ARGUMENTS: {{ARGUMENTS}}

### STEP 0: Parse Arguments

Parse the ARGUMENTS for optional flags:
- `--tests`: Run test optimization analysis only (shape + waste)
- `--docs`: Run doc redundancy analysis only
- `--code`: Run code optimization analysis only (dead code + unused libs)
- `--fix`: Apply automated fixes after detection (requires findings)
- `--quick`: Run quick hygiene sweep (delegates to SweepAnalyzer, same as old `/sweep`)

If no mode flags provided (no --tests, --docs, --code, --quick), run **all three deep modes** (tests + docs + code).

If `--fix` is not provided, this is a dry-run (detect only, no changes).

### STEP 1: Run Analysis

Execute the RefactorAnalyzer to detect optimization opportunities. Run the appropriate analysis based on flags:

```bash
python3 -c "
import sys, json
sys.path.insert(0, 'plugins/autonomous-dev/lib')
from refactor_analyzer import RefactorAnalyzer
from pathlib import Path

analyzer = RefactorAnalyzer(Path('.'))

# Determine mode based on parsed flags
# For --quick: use quick_sweep()
# For specific modes: use full_analysis(['tests']), etc.
# For no flags: use full_analysis() (all modes)

# Example for --quick:
# report = analyzer.quick_sweep()

# Example for specific mode:
# report = analyzer.full_analysis(['tests'])

# Example for all modes:
# report = analyzer.full_analysis()

print(json.dumps(report.to_dict()))
"
```

Capture the JSON output and parse it.

### STEP 2: Present Findings

Display the categorized report. Group findings by category, sort by severity within each group (CRITICAL first, LOW last). Show total counts per category.

**For --tests mode**, also display the test shape distribution table:

```
## Test Shape Distribution (Quality Diamond)

| Type          | Count | Actual% | Target% | Status |
|---------------|-------|---------|---------|--------|
| Unit          | 120   | 75.0%   | 60%     | Over   |
| Integration   | 20    | 12.5%   | 25%     | Under  |
| Property      | 0     | 0.0%    | 5%      | Under  |
| GenAI         | 20    | 12.5%   | 10%     | OK     |
```

Format findings:

```
## Refactor Results

### TEST_SHAPE (N issues)
- [HIGH] tests/: unit tests over-represented: 75% actual vs 60% target
  Suggestion: Reduce unit tests to align with Quality Diamond

### TEST_WASTE (N issues)
- [MEDIUM] tests/test_old.py:10: Trivial test: test_placeholder
  Suggestion: Add meaningful assertions or remove the test

### DOC_REDUNDANCY (N issues)
- [MEDIUM] docs/guide.md: High similarity (92%) between docs/guide.md and docs/tutorial.md
  Suggestion: Consider merging or deduplicating these documents

### DEAD_CODE (N issues)
- [MEDIUM] lib/old_util.py:42: Potentially dead function: legacy_helper
  Suggestion: Remove function 'legacy_helper' if no longer needed

### UNUSED_LIB (N issues)
- [LOW] lib/deprecated.py: Lib module 'deprecated' not imported outside tests
  Suggestion: Archive or remove 'deprecated.py' if no longer needed

Total: X findings across Y categories
```

If **zero findings**: Display "Clean refactor analysis -- no optimization opportunities found." and EXIT.

### STEP 3: Apply Fixes (only if --fix flag provided)

If `--fix` was NOT passed, display: "Run with --fix to apply automated optimizations." and EXIT.

If `--fix` WAS passed, apply fixes by category:

**Test fixes**: Invoke the implementer agent (use Task tool with subagent_type="implementer") with the test findings as context. Instruct it to remove trivial tests, deduplicate test bodies, and reduce over-mocking.

**Doc fixes**: Invoke the doc-master agent (use Task tool with subagent_type="doc-master") with the doc findings as context. Instruct it to merge redundant documents and remove duplicated content.

**Code fixes**: Invoke the implementer agent (use Task tool with subagent_type="implementer") with the code findings as context. Instruct it to remove dead code, archive unused libs, and clean up unreferenced functions.

After all fixes are applied, run a verification:

```bash
python3 -m pytest --tb=short -q 2>&1 | tail -20
```

Verify no regressions were introduced by the fixes.

### STEP 4: Verify

Re-run analysis for the same modes that were originally scanned. Display a before/after comparison:

```
## Before/After Comparison

| Category       | Before | After | Delta |
|----------------|--------|-------|-------|
| Test Shape     | 2      | 0     | -2    |
| Test Waste     | 5      | 1     | -4    |
| Doc Redundancy | 1      | 0     | -1    |
| Dead Code      | 3      | 0     | -3    |
| Unused Libs    | 2      | 1     | -1    |
| Total          | 13     | 2     | -11   |
```

If all findings resolved: "All optimization opportunities addressed."
If some remain: "N findings remain. Run /refactor again to review."
