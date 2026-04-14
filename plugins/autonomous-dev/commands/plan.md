---
name: plan
description: "Create a validated planning document with adversarial critique before implementation"
argument-hint: "Feature description (e.g., '/plan Add JWT authentication for API endpoints')"
allowed-tools: [Task, Read, Bash, Grep, Glob, WebSearch, Write]
disable-model-invocation: false
user-invocable: true
---

# Create Validated Plan

Create a structured planning document with adversarial critique. Plans are written to `.claude/plans/<slug>.md` and validated by the plan_gate hook before implementation.

## Implementation

**CRITICAL**: Follow these steps in order. Each step builds on the previous.

ARGUMENTS: {{ARGUMENTS}}

---

### STEP 0: Parse Arguments

Parse the `{{ARGUMENTS}}` placeholder for the feature description.

If no description provided, prompt the user for a feature description.

---

### STEP 1: Problem Statement (WHY + SCOPE)

Define the problem clearly:

1. **WHY** is this change needed? What problem does it solve?
2. **SCOPE**: What is IN scope and what is OUT of scope?
3. **Success criteria**: How will we know the plan is complete?

Estimate the number of files that will be created or modified.

Invoke the **plan-critic** agent for initial feedback on the problem statement. The plan-critic provides adversarial review to challenge assumptions and find gaps.

---

### STEP 2: Scope Check

Compare the estimated file count from Step 1 against what you discover during research.

**HARD GATE**: If the actual file count exceeds the Step 1 estimate by >50%, halt and re-scope with the user before proceeding.

---

### STEP 3: Existing Solutions

Search for existing solutions before building anything new:

1. **Codebase search**: Use Grep and Glob to find similar patterns
2. **Web search**: Use WebSearch to find libraries, patterns, or prior art
3. **Document findings**: Record what was searched and what was found

This section becomes the "## Existing Solutions" in the plan output.

---

### STEP 4: Minimal Path

Design the smallest change that achieves the goal:

1. List files to create/modify in dependency order
2. Identify what can be deferred to follow-up work
3. Define the critical path

This section becomes the "## Minimal Path" in the plan output.

---

### STEP 5: Adversarial Critique

Invoke the **plan-critic** agent with the full plan draft.

The plan-critic MUST complete minimum 2 critique rounds:
- Round 1: Identify issues across all 5 critique axes
- Round 2: Verify fixes and probe deeper

Verdicts:
- **PROCEED**: Plan is adequate, continue to Step 6
- **REVISE**: Address feedback and re-submit to plan-critic
- **BLOCKED**: Rethink the approach entirely

Do NOT proceed past Step 5 until the plan-critic issues PROCEED.

---

### STEP 6: Issue Decomposition (Required when multi-item)

**HARD GATE**: If the Minimal Path from Step 4 contains **>=2 independent work items**, issue creation is REQUIRED. You MUST create GitHub issues for each independent item before proceeding to Step 7.

**FORBIDDEN**:
- FORBIDDEN: Skipping issue creation when the Minimal Path contains >=2 independent work items
- FORBIDDEN: Declaring work items as "not independent" to avoid issue creation without specific, stated justification
- FORBIDDEN: Proceeding to Step 7 without either creating issues OR logging the single-item skip message below

#### When to create issues (>=2 independent work items):

1. Write each issue body to a temp file and create the command context file:
   ```bash
   python3 -c "
   import json; from datetime import datetime, timezone
   with open('/tmp/autonomous_dev_cmd_context.json', 'w') as f:
       json.dump({'command': 'plan', 'timestamp': datetime.now(timezone.utc).isoformat()}, f)
   "
   ```

2. For each independent work item, create a GitHub issue:
   ```bash
   cat > /tmp/plan_issue_N.md << 'ISSUE_EOF'
   <issue body: title, description, acceptance criteria>
   ISSUE_EOF
   gh issue create --title "feat: <sanitized item title>" --body-file /tmp/plan_issue_N.md
   ```

3. Collect created issue numbers (e.g., `#101`, `#102`).

4. Clean up temp files:
   ```bash
   rm -f /tmp/plan_issue_*.md /tmp/autonomous_dev_cmd_context.json
   ```

**gh CLI unavailability fallback**: If `gh` is not available or authentication fails, log a warning and suggest running `/plan-to-issues` manually after plan creation. Do NOT block the plan file from being written.

#### When to skip (single coherent unit — <2 independent items):

Log the following message and proceed directly to Step 7:

```
Skipping Step 6: plan is a single coherent unit — no issue decomposition needed.
```

Record `N/A — single work item` in the `## Linked Issues` section of the plan file.

---

### STEP 7: Write Plan File

Generate a URL-safe slug from the feature description.

Create the `.claude/plans/` directory if it doesn't exist:
```bash
mkdir -p .claude/plans
```

Write the validated plan to `.claude/plans/<slug>.md` with these required sections:

```markdown
# Plan: <Feature Name>

## WHY + SCOPE
[From Step 1]

## Existing Solutions
[From Step 3]

## Minimal Path
[From Step 4]

## Files to Create/Modify
[From Step 4, ordered by dependency]

## Risks and Unknowns
[Identified during critique]

## Critique History
[Summary of plan-critic rounds and resolutions]

## Linked Issues
[List of created issues: "- #NNN: Title" for each issue, or "N/A — single work item" if no issues were created, or "Issues not created — run `/plan-to-issues`" if gh was unavailable]
```

---

### Output

Display the plan file path and next steps:

```
Plan created: .claude/plans/<slug>.md

Next steps:
  /implement "feature description"            -- implement the plan directly
  /implement --issues #N1,#N2,...             -- implement via linked issues (if issues were created)
  /plan-to-issues                             -- convert plan into GitHub issues (if gh was unavailable)
```

---

## What This Does

| Step | Time | Description |
|------|------|-------------|
| Problem Statement | 1-2 min | Define WHY + SCOPE |
| Scope Check | 30 sec | Validate file count estimate |
| Existing Solutions | 2-3 min | Search codebase + web |
| Minimal Path | 1-2 min | Design smallest change |
| Adversarial Critique | 3-5 min | plan-critic review (2+ rounds) |
| Issue Decomposition | 0-2 min | Optional breakdown |
| Write Plan | 30 sec | Output to .claude/plans/ |
| **Total** | **8-15 min** | Full planning workflow |

---

## Integration

- **plan_gate hook**: Enforces plan existence before complex Write/Edit operations
- **plan-critic agent**: Provides adversarial review during Step 5
- **planning-workflow skill**: Documents the 7-step workflow
- **/plan-to-issues**: Can use `.claude/plans/` files as input source
- **/implement**: Proceeds with implementation after plan is validated
