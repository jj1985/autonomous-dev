# Model Behavior Notes

**Last Updated**: 2026-04-08
**Related**: Issue #108, Issue #728, [docs/AGENTS.md](AGENTS.md), TERMINAL_BENCH_2_GAP_ANALYSIS.md

Known behavioral differences across model tiers and the compensation strategies applied in agent prompts.

---

## Tier Overview

| Tier | Models | Agents | Key Behavioral Tendency |
|------|--------|--------|------------------------|
| Tier 1 | Haiku | researcher-local, test-coverage-auditor, issue-creator | Reasoning preamble before output; low instruction density |
| Tier 2 | Sonnet | reviewer, researcher, doc-master, security-auditor, continuous-improvement-analyst, retrospective-analyst | Silent ambiguity acceptance; assumes intent rather than asking |
| Tier 3 | Opus | planner, implementer, test-master | Over-engineering; requirement inference; subagent spawning |

---

## Opus Behavioral Notes

Opus is a deep-reasoning model optimized for complex synthesis. In agentic coding contexts, this creates specific patterns:

**Over-engineering**: Opus infers additional requirements beyond what was specified, producing solutions more complex than the task demands. A request to "add a config key" may result in a full configuration management subsystem.

**Requirement inference**: Opus extrapolates from the stated requirements to what it thinks the user *actually* wants. This is valuable in open-ended tasks but counterproductive in pipeline contexts where the plan is the spec.

**Subagent spawning**: Opus defaults to delegating subtasks to parallel subagents even when tasks are sequential and simple enough to handle inline.

**Compensation block** (applied to `implementer.md` and `planner.md`):

```xml
<model-tier-compensation tier="opus">
## Model-Tier Behavioral Constraints (Opus)

- Do NOT infer unstated requirements. Execute exactly what the plan describes.
- Do NOT over-engineer solutions. Match the complexity level specified in the plan.
- Do NOT spawn subagents unless the plan explicitly calls for parallelizable work.
- If the plan is ambiguous, implement the simplest interpretation that satisfies acceptance criteria.
</model-tier-compensation>
```

---

## Sonnet Behavioral Notes

Sonnet is a balanced reasoning model optimized for judgment tasks. In review contexts, this creates specific patterns:

**Silent ambiguity acceptance**: Sonnet tends to assume the most charitable interpretation of ambiguous code rather than flagging it. Code that *could* be a bug or could be intentional gets a pass.

**Assumption over inquiry**: When context is missing, Sonnet fills in the gap with assumptions rather than surfacing what it cannot determine.

**Compensation block** (applied to `reviewer.md`):

```xml
<model-tier-compensation tier="sonnet">
## Model-Tier Behavioral Constraints (Sonnet)

- Be explicit about what you cannot determine from the given context.
- If code behavior is ambiguous, flag it as a FINDING rather than assuming intent.
- Do NOT silently accept patterns that could be bugs or could be intentional — ask via REQUEST_CHANGES.
</model-tier-compensation>
```

---

## Haiku Behavioral Notes

Haiku is a fast, cost-effective model optimized for pattern matching. In research contexts, this creates specific patterns:

**Reasoning preamble**: Haiku produces conversational preamble ("Let me search for that...") before returning structured output, adding noise to machine-readable responses.

**Low instruction density**: Haiku follows simpler instructions more reliably than dense multi-step instructions. Complex research protocols benefit from explicit enumeration.

**Compensation block** (applied to `researcher-local.md`):

```xml
<model-tier-compensation tier="haiku">
## Model-Tier Behavioral Constraints (Haiku)

1. Search using at least 3 different grep patterns per research question.
2. Return structured JSON output — no reasoning preamble.
3. If zero results found, report what was searched and why it failed.
</model-tier-compensation>
```

---

## Compensation Pattern Design

### XML Tag Format

Compensation blocks use `<model-tier-compensation tier="...">` XML tags for several reasons:

1. **Machine-readable**: The `tier` attribute allows automated validation that the block matches the agent's declared model tier in frontmatter.
2. **Visually distinct**: XML tags separate behavioral constraints from role description, preventing the model from treating constraints as part of its identity.
3. **Grepping**: Tests can check for the exact tag string without parsing the full document.

### Security Notes

Compensation blocks MUST NOT contain:

- Meta-commentary about model weaknesses (e.g., "Opus tends to fail at X") — this is model-visible prompt content and may reinforce the described behavior
- References to competitor models
- Derogatory or negative framing of the model's capabilities

Blocks SHOULD contain:

- Actionable behavioral directives (DO NOT X, ALWAYS Y)
- Specific enough instructions to be testable
- Positive framing where possible ("implement the simplest interpretation" rather than "don't over-complicate")

---

## Prompt Word Selection

The words used in agent prompts shift how deeply the model applies a constraint — a phenomenon called **register shifting**. This directly affects whether behavioral constraints in compensation blocks are followed or ignored.

### Register Tier Taxonomy

| Tier | Words | Effect |
|------|-------|--------|
| **Tier 1 — Deep** | `audit`, `verify`, `critically analyse`, `enumerate` | Systematic scan, high compute allocation |
| **Tier 2 — Balanced** | `review`, `check`, `describe`, `summarize` | Standard processing |
| **Tier 3 — Minimal** | `look at`, `mention`, `note`, `consider` | Advisory; easily skipped under cognitive load |

**Rule**: Hard gates and FORBIDDEN lists must use Tier 1 verbs. Tier 3 verbs in enforcement contexts produce near-zero compliance.

### Anti-Pattern: Persona Prefixes for Analytical Tasks

**Source**: PRISM (arxiv:2603.18507) — expert persona prefixes reduce knowledge-retrieval accuracy for analytical tasks.

The pattern `"You are a senior [role]..."` allocates model attention to maintaining the persona rather than applying domain knowledge. For reviewers, auditors, and analytical agents, this degrades output quality.

**FORBIDDEN for analytical agents**: `You are a [role]...`, `Act as an expert in...`, `Imagine you are...`

**Correct pattern**: Role description + behavioral directive without persona framing.

```
# BAD — persona prefix
You are a senior security engineer with 10 years of experience. Review this code.

# GOOD — directive without persona
Perform a security audit of the changed files. Enumerate all CWE categories present.
```

**Cross-reference**: [docs/PROMPT-ENGINEERING.md](PROMPT-ENGINEERING.md) contains the full PRISM finding, constraint budget analysis (MOSAIC), and complete register shifting taxonomy.

---

## References

- Issue #108: Model tier strategy — original tier assignments and rationale
- Issue #728: Model-specific prompt compensation — this implementation
- [docs/AGENTS.md](AGENTS.md): Agent architecture and tier assignments
- TERMINAL_BENCH_2_GAP_ANALYSIS.md: Benchmark analysis informing tier behavioral patterns
