---
name: sweep
description: "Alias for /refactor --quick — codebase hygiene sweep"
argument-hint: "[--fix]"
user-invocable: true
allowed-tools: [Read, Bash, Grep, Glob, Agent]
---

# Codebase Hygiene Sweep (Alias)

This command is an alias for `/refactor --quick`. It runs a quick hygiene sweep using the SweepAnalyzer through the RefactorAnalyzer orchestrator.

## Implementation

ARGUMENTS: {{ARGUMENTS}}

This command redirects to `/refactor --quick`. Pass any additional flags through:

- If `--fix` was provided: Run `/refactor --quick --fix`
- Otherwise: Run `/refactor --quick`

**Action**: Invoke the `/refactor` command with `--quick` prepended to any provided arguments. Do NOT run independent analysis logic — delegate entirely to `/refactor`.
