---
name: sweep
description: "Codebase hygiene -- detect and fix dead tests, doc drift, code rot"
argument-hint: "[--tests] [--docs] [--code] [--fix]"
user-invocable: true
---

# Codebase Hygiene Sweep

Detect and optionally fix dead tests, documentation drift, and code rot. Uses existing detection libraries (TechDebtDetector, HybridManifestValidator, OrphanFileCleaner) through the SweepAnalyzer orchestrator.

## Implementation

ARGUMENTS: {{ARGUMENTS}}

### STEP 0: Parse Arguments

Parse the ARGUMENTS for optional flags:
- `--tests`: Run test hygiene detection only
- `--docs`: Run documentation drift detection only
- `--code`: Run code rot detection only
- `--fix`: Apply automated fixes after detection (requires findings)

If no mode flags provided (no --tests, --docs, --code), run **all three modes** (tests + docs + code).

If `--fix` is not provided, this is a dry-run (detect only, no changes).

### STEP 1: Run Detection

Execute the SweepAnalyzer to detect hygiene issues. Run the appropriate analysis based on flags:

```bash
python3 -c "
import sys, json
sys.path.insert(0, 'plugins/autonomous-dev/lib')
from sweep_analyzer import SweepAnalyzer, SweepCategory
from pathlib import Path

analyzer = SweepAnalyzer(Path('.'))

# Determine which modes to run based on flags
# If specific modes requested, run only those; otherwise run all
modes = []
findings = []

# Replace these conditionals based on parsed flags:
# For --tests only: modes = ['tests']
# For --docs only: modes = ['docs']
# For --code only: modes = ['code']
# For no flags: modes = ['tests', 'docs', 'code']

if 'tests' in modes or not modes:
    findings.extend(analyzer.analyze_tests())
    modes.append('tests') if 'tests' not in modes else None
if 'docs' in modes or not modes:
    findings.extend(analyzer.analyze_docs())
    modes.append('docs') if 'docs' not in modes else None
if 'code' in modes or not modes:
    findings.extend(analyzer.analyze_code())
    modes.append('code') if 'code' not in modes else None

report_data = {
    'findings': [
        {
            'file': f.file_path,
            'line': f.line,
            'category': f.category.value,
            'severity': f.severity.value,
            'description': f.description,
            'fix': f.suggested_fix
        }
        for f in findings
    ],
    'summary': {},
    'duration_ms': 0,
    'modes_run': modes
}

# Build summary
for f in findings:
    cat = f.category.value
    report_data['summary'][cat] = report_data['summary'].get(cat, 0) + 1

print(json.dumps(report_data))
"
```

Capture the JSON output and parse it.

### STEP 2: Present Findings

Display the categorized report. Group findings by category (**Tests** / **Docs** / **Code**), sort by severity within each group (CRITICAL first, LOW last). Show total counts per category.

Format:

```
## Sweep Results

### Tests (N issues)
- [CRITICAL] path/to/test.py: Failing test: test_something
  Fix: Fix or remove the failing test
- [HIGH] ...

### Docs (N issues)
- [HIGH] CLAUDE.md: Agent count mismatch
  Fix: Update documentation

### Code (N issues)
- [MEDIUM] path/to/file.py: Orphaned file
  Fix: Remove or add to manifest

Total: X findings across Y categories
```

If **zero findings**: Display "Clean sweep -- no hygiene issues found." and EXIT.

### STEP 3: Apply Fixes (only if --fix flag provided)

If `--fix` was NOT passed, display: "Run with --fix to apply automated repairs." and EXIT.

If `--fix` WAS passed, apply fixes by category:

**Test fixes**: Invoke the implementer agent (use Task tool with subagent_type="implementer") with the test findings as context. Instruct it to fix failing tests, update imports from archived modules, and reduce brittle assertions.

**Doc fixes**: Invoke the doc-master agent (use Task tool with subagent_type="doc-master") with the doc findings as context. Instruct it to update component counts, fix cross-references, and resolve documentation drift.

**Code fixes**: Invoke the implementer agent (use Task tool with subagent_type="implementer") with the code findings as context. Instruct it to remove dead imports, clean up orphaned files, and reduce complexity.

After all fixes are applied, run a verification:

```bash
python3 -m pytest --tb=short -q 2>&1 | tail -20
```

Verify no regressions were introduced by the fixes.

### STEP 4: Verify

Re-run detection for the same modes that were originally scanned. Display a before/after comparison:

```
## Before/After Comparison

| Category | Before | After | Delta |
|----------|--------|-------|-------|
| Tests    | 5      | 1     | -4    |
| Docs     | 3      | 0     | -3    |
| Code     | 7      | 2     | -5    |
| Total    | 15     | 3     | -12   |
```

If all findings resolved: "All hygiene issues resolved."
If some remain: "N findings remain. Run /sweep again to review."
