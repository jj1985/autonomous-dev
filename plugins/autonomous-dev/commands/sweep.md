---
name: sweep
description: "Codebase hygiene sweep — /refactor --quick alias, or --tests for test pruning analysis"
argument-hint: "[--fix] [--tests]"
user-invocable: true
allowed-tools: [Read, Bash, Grep, Glob, Agent]
---

# Codebase Hygiene Sweep

This command has two modes:

1. **Default mode** (no `--tests`): Alias for `/refactor --quick` — runs a quick hygiene sweep using the SweepAnalyzer through the RefactorAnalyzer orchestrator.
2. **Test pruning mode** (`--tests`): Runs the TestPruningAnalyzer to detect orphaned, stale, and redundant tests.

## Implementation

ARGUMENTS: {{ARGUMENTS}}

### Mode Selection

**If `--tests` is in the arguments**:

Run the TestPruningAnalyzer directly. Execute the following Python script via Bash:

```bash
cd {{PROJECT_ROOT}} && python3 -c "
import sys
sys.path.insert(0, 'plugins/autonomous-dev/lib')
from test_pruning_analyzer import TestPruningAnalyzer
from pathlib import Path

analyzer = TestPruningAnalyzer(Path('.'))
report = analyzer.analyze()
print(report.format_table())
"
```

Display the resulting markdown table to the user. This is an **informational report only** — never auto-delete any files.

After displaying results, suggest:
- Review HIGH severity findings first
- Files marked `prunable=yes` (T2/T3 tier) are safe candidates for removal
- Files marked `prunable=no` (T0/T1 tier) should NOT be removed without careful review

**If `--tests` is NOT in the arguments** (default mode):

This command redirects to `/refactor --quick`. Pass any additional flags through:

- If `--fix` was provided: Run `/refactor --quick --fix`
- Otherwise: Run `/refactor --quick`

**Action**: Invoke the `/refactor` command with `--quick` prepended to any provided arguments. Do NOT run independent analysis logic — delegate entirely to `/refactor`.
