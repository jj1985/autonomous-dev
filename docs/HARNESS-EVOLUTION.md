---
covers:
  - plugins/autonomous-dev/config/component_classifications.json
---

# Harness Evolution Tracking

This document describes the classification system for enforcement components in the autonomous-dev harness, enabling systematic review when model capabilities improve.

## Purpose

The autonomous-dev harness contains dozens of enforcement mechanisms: hooks, hard gates, and forbidden lists. Some exist because **the model has behavioral limitations** (e.g., skipping tests, stubbing code). Others exist because **the process requires them** regardless of model capability (e.g., security scanning, code formatting).

When a new model version ships with improved capabilities, the team needs to know which enforcement components are candidates for removal or relaxation, and which must stay regardless.

## Classification Values

### model-limitation

Components that exist because the model exhibits specific failure patterns under certain conditions. Each entry includes `removal_criteria` -- the observable behavior change that would make the component unnecessary.

**Examples**: enforce_tdd (model writes code before tests), stop_quality_gate (model declares done prematurely), no-new-skips gate (model adds skip markers to game test gates).

### process-requirement

Components that enforce engineering standards, security practices, or operational needs that are independent of model capability. These have `removal_criteria: null` because they should never be removed due to model improvements alone.

**Examples**: security_scan (always required), auto_format (code style standard), session_activity_logger (audit trail).

## Registry Location

The central registry is at:

```
plugins/autonomous-dev/config/component_classifications.json
```

The JSON schema is at:

```
plugins/autonomous-dev/config/component_classifications.schema.json
```

## Model Upgrade Review Checklist

When evaluating a new model version, follow this process:

1. **Run the validation script** to ensure the registry is current:
   ```bash
   python scripts/validate_component_classifications.py
   ```

2. **Filter model-limitation entries** from the registry. These are the only candidates for removal.

3. **For each model-limitation entry**, evaluate the `removal_criteria`:
   - Run the model on 50+ real sessions without the enforcement
   - Track whether the model exhibits the limitation behavior
   - Document results in the entry's `review_status`

4. **Update review_status** based on findings:
   - `reviewed` -- evaluated, still needed
   - `candidate-for-removal` -- model no longer exhibits the limitation
   - `removed` -- enforcement removed after validation

5. **Do not touch process-requirement entries** during model-upgrade reviews. They are model-independent by definition.

6. **Update `last_reviewed` date** in the registry after completing the review.

## How to Propose Removing a model-limitation Component

1. Verify the entry has `classification: "model-limitation"`
2. Run a controlled experiment:
   - Disable the enforcement for 50+ real sessions
   - Track failure rate (does the model still exhibit the limitation?)
   - Compare to baseline failure rate with enforcement enabled
3. If failure rate is below threshold (typically <5%):
   - Set `review_status` to `candidate-for-removal`
   - Open a GitHub issue documenting the experiment results
   - Get team approval before removing
4. After approval:
   - Remove the enforcement code
   - Set `review_status` to `removed`
   - Keep the registry entry for historical tracking

## How to Add New Components

When adding a new hook, hard gate, or forbidden list:

1. Determine classification:
   - Does the model exhibit a specific failure pattern that this prevents? -> `model-limitation`
   - Is this an engineering/security/process standard? -> `process-requirement`

2. Add the entry to the appropriate section in `component_classifications.json`

3. For `model-limitation` entries, define concrete `removal_criteria`

4. For `process-requirement` entries, set `removal_criteria: null`

5. Run the validation script to verify:
   ```bash
   python scripts/validate_component_classifications.py
   ```

## Decision Tree: When to Reclassify

```
Is the enforcement preventing a model behavioral issue?
  YES -> model-limitation
    Has the model improved enough to not need it?
      YES -> candidate-for-removal (after experiment)
      NO  -> keep as model-limitation
  NO  -> Is it an engineering/security/process standard?
    YES -> process-requirement (never remove for model reasons)
    NO  -> Re-evaluate whether the component is needed at all
```

## Review Status Values

| Status | Meaning |
|--------|---------|
| `initial` | Newly classified, not yet reviewed against a newer model |
| `reviewed` | Evaluated against a newer model, still needed |
| `candidate-for-removal` | Model no longer exhibits the limitation, pending approval |
| `removed` | Enforcement removed, entry kept for history |
