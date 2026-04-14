---
covers:
  - plugins/autonomous-dev/agents/
  - plugins/autonomous-dev/skills/
---

# Prompt Engineering Reference

Empirically-grounded patterns for writing agent prompts and skill files. Based on MOSAIC constraint research, PRISM persona findings, Self-Refine NeurIPS 2023, and production observations from this codebase.

**Last Updated**: 2026-04-14
**Related**: [docs/model-behavior-notes.md](model-behavior-notes.md), [plugins/autonomous-dev/skills/prompt-engineering/SKILL.md](../plugins/autonomous-dev/skills/prompt-engineering/SKILL.md)

---

## Constraint Budget

**Source**: MOSAIC (arxiv:2601.18554) — constraint count vs. compliance rate empirical study.

| Range | Behavior | Recommendation |
|-------|----------|----------------|
| 1–6 constraints | Reliable compliance | Safe zone for hard gates |
| 7–15 constraints | Unpredictable — partial compliance, constraint blending | Avoid; split into sections |
| >15 constraints | Degraded — model ignores or blends constraints | Never in a single section |

**Rule**: Max 6 hard constraints per section. Enforce with FORBIDDEN/REQUIRED lists, not inline prose.

**Recency Effect (Claude-specific)**: Claude shows higher compliance with instructions placed at the END of sections. Hard gates and FORBIDDEN lists belong at the end of a section, not the beginning. Opening with context and closing with constraints matches Claude's attention pattern.

**Practical implication**: If a HARD GATE section has both FORBIDDEN and REQUIRED lists, FORBIDDEN goes last — it has the highest priority and benefits most from recency.

---

## Register Shifting

**Source**: Production observations documented in [docs/model-behavior-notes.md](model-behavior-notes.md), Issue #728.

Word choice shifts the model's processing register — how deeply it applies a constraint. The tier taxonomy:

| Tier | Words | Effect | When to Use |
|------|-------|--------|-------------|
| **Tier 1 — Deep** | `audit`, `verify`, `critically analyse`, `enumerate` | Forces systematic scan, compute allocation | Hard gates, security checks, enforcement |
| **Tier 2 — Balanced** | `review`, `check`, `describe`, `summarize` | Standard processing, produces adequate output | Most task instructions |
| **Tier 3 — Minimal** | `look at`, `mention`, `note`, `consider` | Advisory; easily skipped under cognitive load | Soft suggestions only |

**Rule**: Use Tier 1 for hard gates. Use Tier 3 only for explicitly optional steps. Never use Tier 3 where compliance is required.

**Anti-pattern**: Mixing tiers in the same constraint — "review the code and verify security" creates ambiguity about which tier applies to the combined instruction.

---

## Persona Anti-Pattern

**Source**: PRISM (arxiv:2603.18507) — persona effects on knowledge retrieval accuracy.

PRISM finding: Injecting expert persona prefixes ("You are a senior security engineer...") **reduces** knowledge-retrieval accuracy for analytical tasks. The model allocates attention to maintaining the persona rather than applying domain knowledge.

**FORBIDDEN for analytical agents** (reviewers, auditors, analysts):
- `You are a [role]...` prefixes
- `Act as an expert in...` framing
- `Imagine you are...` setups

**Correct pattern**: Role description + behavioral directive, without persona framing.

```
# BAD — persona prefix (PRISM finding: reduces accuracy)
You are a senior security engineer with 10 years of experience. Review this code for vulnerabilities.

# GOOD — role description + behavioral directive
Perform a security audit of the changed files. Enumerate all CWE categories present.
Use Tier 1 language (audit, enumerate, verify) for the scan, not advisory review.
```

**When persona IS acceptable**: Creative or generative tasks (writing, brainstorming) where maintaining a voice is the goal, not analytical accuracy.

---

## Self-Refine Loop

**Source**: Self-Refine (NeurIPS 2023) — iterative refinement with self-feedback.

Self-Refine demonstrated ~20% quality improvement using a GENERATE → FEEDBACK → REFINE cycle. Optimal: 2–3 passes. Diminishing returns after 3.

**Pattern**:

```
## Pass 1: GENERATE
Produce the initial output without self-critique.

## Pass 2: FEEDBACK
Critically analyse the Pass 1 output. Enumerate:
- Gaps (what is missing)
- Errors (what is wrong)
- Ambiguities (what is unclear)

## Pass 3: REFINE
Apply Pass 2 feedback. Produce final output.
```

**When to use in agent prompts**: For tasks where the first pass is expected to be incomplete — planning, architecture, security scans. Over-use adds token cost without quality gains for straightforward tasks.

**Anti-pattern**: Asking for self-refinement without a concrete feedback criterion. "Review your answer and improve it" is Tier 3 and will be ignored. "Critically analyse for gaps and enumerate missing cases" is Tier 1 and will be executed.

---

## XML Sectioning

**Source**: Anthropic context engineering guide — structured context boundaries.

XML tags create clean context boundaries that reduce interference between sections. Used throughout this codebase for model-tier compensation.

**Format**:

```xml
<model-tier-compensation tier="opus">
## Model-Tier Behavioral Constraints (Opus)

- Do NOT infer unstated requirements. Execute exactly what the plan describes.
- Do NOT over-engineer solutions. Match the complexity level specified in the plan.
</model-tier-compensation>
```

**Rules**:
- Tag names should be semantically meaningful (`model-tier-compensation`, not `div` or `section`)
- Include `tier` attribute for compensation blocks — allows automated validation
- Keep content inside tags focused on one concern
- Do NOT nest compensation blocks — one block per section

**Why it works**: XML tags signal to the model that the enclosed content is a distinct context unit, reducing bleed between role description and behavioral constraints.

---

## Minimal High-Signal Tokens

Every token in a prompt competes for attention. Filler tokens dilute constraint signal.

**Rules**:
1. Cut preamble — "As you complete this task, please remember to..." → delete
2. Cut hedge language — "try to", "ideally", "if possible", "when appropriate" → delete or replace with REQUIRED
3. Cut meta-commentary — "Note that this is important" → the constraint IS the note
4. Prefer lists over prose for constraints — lists have higher compliance than embedded sentences
5. Use active imperative voice — "Verify X" not "X should be verified"

**Before/After**:

```
# BEFORE (low-signal)
When you are reviewing code, it's important that you try to carefully look at security
issues, and ideally you should note any potential problems you find. Please also try
to check for performance issues if possible.

# AFTER (high-signal)
Audit for:
1. Security vulnerabilities (enumerate by CWE category)
2. Performance anti-patterns (O(n²) loops, unbounded allocations)
```

---

## HARD GATE Patterns

**Source**: Production enforcement observations — this codebase since 2025.

HARD GATE sections have a specific structure that maximizes compliance. The pattern is used across all agent prompts in this codebase.

### Naming Convention

Section headers use "HARD GATE: [Topic]" to signal non-negotiable enforcement. The exact phrase triggers higher compliance than softer headers ("Important:", "Note:", "Warning:").

### Structure Template

```markdown
### HARD GATE: [Topic Name]

**[One-sentence scope statement]**

**REQUIRED** (all must be met):
- Specific action A
- Specific action B
- Specific action C

**FORBIDDEN** — You MUST NOT do any of the following:
- ❌ You MUST NOT [specific prohibited action]
- ❌ You MUST NOT [specific prohibited action]
- ❌ You MUST NOT [specific prohibited action]

**Why**: [One-sentence justification — the "why" increases compliance]
```

### JSON Decision Format for Hooks

Hooks use JSON output instead of exit codes for blocking decisions. JSON is model-readable and includes structured carrot directives:

```json
{
  "decision": "block",
  "reason": "No validated plan found for this changeset. Plan required before Write/Edit to agents/*.md.",
  "requiredNextAction": "Run /plan to create a validated plan, then retry this operation."
}
```

Rules for hook JSON:
- `decision`: `"block"` or `"approve"` — never exit code 2
- `reason`: What failed and why — model reads this
- `requiredNextAction`: The CARROT — what to do next (stick+carrot pattern)

### Stick+Carrot Pattern

Every block must include a carrot: a specific next action the model can take. A block without a next action creates a dead end and the model loops.

```
# STICK only (bad)
BLOCKED: Cannot edit agents/*.md outside the pipeline.

# STICK + CARROT (good)
BLOCKED: Cannot edit agents/*.md outside the pipeline.
REQUIRED NEXT ACTION: Use /implement to run the pipeline with your changes as the feature description.
```

---

## Anti-Patterns

### Meta-Commentary About Model Weaknesses

Describing a model's tendency in a prompt visible to that model may reinforce the behavior.

```
# BAD — self-fulfilling
# (in Opus agent prompt)
Note: Opus tends to over-engineer solutions, so be careful not to over-engineer.

# GOOD — behavioral directive without framing the weakness
Do NOT infer unstated requirements. Execute exactly what the plan describes.
```

### Persona Prefixes for Analytical Tasks

See [Persona Anti-Pattern](#persona-anti-pattern) above. PRISM (arxiv:2603.18507) shows accuracy reduction.

### Exceeding the Constraint Budget

Putting >15 constraints in one section. Split into sub-sections, each with ≤6 hard constraints.

### Hedge Words in Hard Gates

Words like "try", "ideally", "prefer", "consider", "if possible" in a HARD GATE section. Either the constraint is required or it isn't. If required, use "MUST". If optional, use a SHOULD section, not a HARD GATE.

### Advisory Text as Enforcement

Using comment-style prose to enforce behavior ("Note: tests are important"). Prose is Tier 3. Hard gates need FORBIDDEN/REQUIRED structure.

### Stacking Independent Instructions in Prose

Burying multiple constraints in a paragraph. Lists have higher compliance. Break prose into enumerated lists.

---

## References

- **MOSAIC** (arxiv:2601.18554): "Measuring Constraint Compliance in LLM Outputs" — constraint budget empirical study. Establishes the 1–6/7–15/>15 compliance zones.
- **PRISM** (arxiv:2603.18507): "Persona Role-play Impacts on Structured Modeling" — expert persona prefixes reduce knowledge-retrieval accuracy for analytical tasks.
- **Self-Refine** (NeurIPS 2023, Madaan et al.): Iterative self-refinement with feedback demonstrates ~20% quality improvement over single-pass generation. Optimal 2–3 passes.
- **Anthropic Context Engineering**: Internal documentation on XML sectioning and context boundary management (referenced in official Claude documentation).
- [docs/model-behavior-notes.md](model-behavior-notes.md): Per-tier behavioral patterns and compensation block templates.
- [feedback_stick_carrot_pattern.md](../.claude/memory/feedback_stick_carrot_pattern.md): Production stick+carrot enforcement observations.
