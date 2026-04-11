# Mutation Testing Baseline Report

**Date captured**: TBD (run `bash scripts/run_mutation_tests.sh` to capture actual scores)

**Tool**: mutmut >= 2.4.0

**Target**: `plugins/autonomous-dev/lib/` (critical files only)

## Baseline Scores

| File | Total Mutants | Killed | Survived | Timeout | Score | Notes |
|------|--------------|--------|----------|---------|-------|-------|
| pipeline_state.py | TBD | TBD | TBD | TBD | TBD | State machine, gate conditions |
| tool_validator.py | TBD | TBD | TBD | TBD | TBD | Security validation, whitelist/blacklist |
| settings_generator.py | TBD | TBD | TBD | TBD | TBD | Pattern generation, deny list |

**Target**: 70%+ mutation score on critical files.

## How to Capture Baseline

```bash
# Run mutation tests against the three critical files
bash scripts/run_mutation_tests.sh

# Run against a single file
bash scripts/run_mutation_tests.sh --file plugins/autonomous-dev/lib/pipeline_state.py

# Run in CI mode (summary output)
bash scripts/run_mutation_tests.sh --ci
```

## Equivalent Mutant Notes

The following mutant types are expected to survive and should NOT be chased:

- **String literal mutations**: Changing `"error"` to `"XXerrorXX"` rarely affects behavior. These are equivalent mutants in most cases.
- **Magic number mutations**: Changing `0o600` to `0o601` in permission constants is only meaningful if tests check file permissions explicitly.
- **Return value mutations on void-like functions**: Functions that return None or have side-effect-only behavior.

## High-Value Surviving Mutants (prioritize killing)

1. **Conditional mutations** (`<` to `<=`, `==` to `!=`): Indicate missing boundary tests
2. **Arithmetic mutations** (`+` to `-`, `*` to `/`): Indicate missing calculation tests
3. **Boolean mutations** (`True` to `False`, `and` to `or`): Indicate missing logic tests

## Recovery

If mutation cache becomes corrupted:
```bash
mutmut run --no-cache
# Or clear manually:
rm -rf .mutmut-cache/
```
