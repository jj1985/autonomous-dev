---
covers:
  - plugins/autonomous-dev/agents/
  - plugins/autonomous-dev/skills/
  - plugins/autonomous-dev/lib/
  - plugins/autonomous-dev/hooks/
  - plugins/autonomous-dev/commands/
---

# Architecture Overview

Complete technical architecture for the autonomous-dev plugin, including agents, skills, libraries, hooks, and model tier strategy.

**Component Counts**: 13 agents (18 archived), 17 skills, 21 active commands, 190 libraries, 25 active hooks (62 archived).

---

## Agents

Specialized agents with skill integration for autonomous development. See [docs/AGENTS.md](docs/AGENTS.md) for complete details. See component counts at the top of this file.

**Key Features**:
- Native skill integration (Issue #143): Agents declare skills via `skills:` frontmatter field - Claude Code 2.0 auto-loads skills when agent spawned
- Adaptive STEP 10 validation: parallel mode by default (all three agents launched simultaneously for low-risk changesets); sequential mode for security-sensitive files (reviewer → security-auditor strict ordering, doc-master in background alongside reviewer)
- Pipeline agents used in `/implement`, utility agents for specialized tasks

---

## Model Tier Strategy

Agent model assignments optimized for cost-performance balance (13 active agents):

**Tier 1 (Haiku)** - Fast, cost-effective for pattern matching
- researcher-local - Search codebase patterns
- test-coverage-auditor - AST-based coverage analysis
- issue-creator - GitHub issue creation

**Tier 2 (Sonnet)** - Balanced reasoning for judgment tasks
- researcher - Web research and synthesis
- reviewer - Code quality gate (10-point checklist)
- security-auditor - OWASP security scanning
- doc-master - Semantic documentation drift detection
- continuous-improvement-analyst - Pipeline QA and gaming detection
- retrospective-analyst - Intent evolution and session drift detection
- ui-tester - E2E browser testing via Playwright MCP (optional, STEP 9.7)

**Tier 3 (Opus)** - Deep reasoning for complex synthesis
- planner - Architecture planning
- implementer - Code implementation
- test-master - Quality Diamond test generation

**Performance Impact**: Optimized tier assignments reduce costs by 40-60% while maintaining quality.

---

## Skills

Specialized skill packages using progressive disclosure to prevent context bloat. See component counts at the top of this file.

**How It Works**:
- Agents declare skills in `skills:` frontmatter field, auto-loaded when spawned
- Each skill declares `allowed-tools:` for least privilege
- Compact SKILL.md files with detailed content in docs/ subdirectories

**Active Skills** (17 total):
- **Core**: python-standards, testing-guide, api-design, documentation-guide
- **Code Quality**: code-review, refactoring-patterns
- **Error & Debugging**: error-handling, debugging-workflow
- **Security & Observability**: security-patterns, observability
- **Integration & Design**: library-design-patterns, api-integration-patterns, state-management-patterns, architecture-patterns
- **Workflow & Research**: git-github, research-patterns
- **Validation**: scientific-validation

---

## Libraries

Reusable Python libraries for security, validation, automation, and more. See [docs/LIBRARIES.md](docs/LIBRARIES.md) for complete API documentation.

**Design Pattern**: Progressive enhancement, two-tier design (core logic + CLI), non-blocking enhancements

**Key Libraries**:
- **Security**: security_utils.py, mcp_security.py, sandbox_enforcer.py, agent_ordering_gate.py (pure-logic pipeline ordering decisions — no I/O)
- **Validation**: validation.py, alignment_validator.py, project_validator.py
- **Automation**: unified_git_automation.py (git operations), batch_processor.py, session_tracker.py
- **State Management**: session_state_manager.py (session persistence), batch_state_manager.py, user_state_manager.py, session_resource_manager.py (resource tracking), pipeline_state.py (pipeline progression tracking), pipeline_completion_state.py (agent ordering enforcement state — written by session tracker, read by pre-tool hook)
- **Infrastructure**: path_utils.py, performance_timer.py, agent_tracker.py, pipeline_timing_analyzer.py, test_pruning_analyzer.py (AST-based test hygiene — detects orphaned imports, archived refs, zero-assertion tests, duplicate coverage, and stale regressions; used by `/sweep --tests`), test_issue_tracer.py (test-to-issue traceability — maps tests to GitHub issues, flags untested issues, orphaned pairs, and untraced tests; used by `/audit --test-tracing` and STEP 13 non-blocking warning)
- **See**: [docs/LIBRARIES.md](docs/LIBRARIES.md) for complete API reference

**Note on auto_git_workflow.py**: A backward compatibility shim exists at `.claude/hooks/auto_git_workflow.py` (56 lines) that redirects to `unified_git_automation.py`. The original hook was consolidated in Issue #144. Duplicate resolution completed in Issue #212. See `plugins/autonomous-dev/hooks/archived/README.md` for details.

---

## Hooks

Unified hooks using dispatcher pattern for quality enforcement. See [docs/HOOKS.md](docs/HOOKS.md) for complete reference.

**Hook Registration**: Hooks declare lifecycle events and configurations via `.hook.json` sidecar files (Issue #551). See [docs/HOOK-SIDECAR-SCHEMA.md](docs/HOOK-SIDECAR-SCHEMA.md) for the declarative metadata schema (lifecycle events, matchers, timeouts, environment variables, type semantics).

**Key Features**: Dispatcher pattern (env var control), graceful degradation (non-blocking), backward compatible

**Hook Output Visibility** (Issue #660): `permissionDecisionReason` on deny is model-visible — block messages include `REQUIRED NEXT ACTION:` carrots that the model reads and acts on. `systemMessage` is user-visible (injected into the conversation). These are distinct channels: enforcement directives belong in `permissionDecisionReason`; user notifications belong in `systemMessage`. See [docs/HOOKS.md](docs/HOOKS.md) for full output format specification.

**Active Hooks**:
- **PreToolUse**: unified_pre_tool.py (4-layer MCP validation: Sandbox → MCP Security → Agent Auth → Batch Permission; native tools bypass MCP layers but Agent/Task tool calls also pass through the Pipeline Ordering Gate before extensions — Issues #625, #629, #632)
- **PrePromptSubmit**: unified_prompt_validator.py (workflow enforcement)
- **PostToolUse**: auto_format.py, auto_test.py, security_scan.py, auto_fix_docs.py
- **PreCommit**: validate_project_alignment.py, enforce_orchestrator.py, enforce_tdd.py, validate_session_quality.py
- **See**: [docs/HOOKS.md](docs/HOOKS.md) for complete hook reference

---

## Workflow Pipeline

**Autonomous Development Workflow** (15 steps):

1. **Alignment Check**: Verify feature aligns with PROJECT.md
2. **Complexity Assessment** (v3.45.0): complexity_assessor determines pipeline scaling
   - Recommends agent count (3/6/8) and time (8/15/25 min)
   - Based on SIMPLE/STANDARD/COMPLEX classification
3. **Research**: researcher agent finds patterns (Haiku model)
4. **Planning**: planner agent creates architecture plan
5. **Pause Control** (v3.45.0): Optional human-in-the-loop after planning
6. **Acceptance Tests** (Issue #404, default): test-master writes specification-driven acceptance tests
   - Default mode: validation-first approach (specification → acceptance tests → implementation)
   - Optional `--tdd-first` flag reverts to legacy TDD-first (failing unit tests first)
7. **Implementation**: implementer makes tests pass
7.5. **E2E UI Testing** (STEP 9.7, Issue #656, optional): ui-tester writes Playwright MCP browser tests
   - Only invoked when changed files include frontend patterns AND Playwright MCP is available
   - Advisory only — PASS or SKIP, never blocks the pipeline
8. **Validation** (implement.md STEP 10) — mode selected based on changeset risk:
   - **Parallel mode** (default): reviewer, security-auditor, and doc-master launched simultaneously in one message (low-risk changesets with no security-sensitive files)
   - **Sequential mode** (security-sensitive files): reviewer runs first (10a), security-auditor runs only after reviewer returns (10b), doc-master runs in background alongside reviewer (10c)
   - reviewer consumes STEP 8 test artifact (pytest results passed in context) — does NOT re-run pytest
   - doc-master runs non-blocking in both modes; result collected at STEP 12 — unless remediation occurred (see 8.5 below)
8.5. **Remediation Gate** (HARD GATE): If reviewer or security-auditor return findings, auto-loop:
   - Re-invokes implementer in Remediation Mode with BLOCKING findings verbatim (max 2 cycles)
   - Re-runs only the failing validators after each cycle (doc-master excluded from remediation loop)
   - Files GitHub issues and blocks pipeline if findings persist after 2 cycles
   - **Remediation-Aware Doc-Drift (STEP 12)**: If remediation occurred, the STEP 10 background doc-master result is discarded as stale; STEP 12 discards it and re-invokes doc-master BLOCKING with a fresh `git diff` file list reflecting post-remediation changes (#624)
9. **Memory Recording** (v3.45.0): Cross-session context after validation
10. **Automated Git Operations**: SubagentStop hook handles commit/push/PR
11. **Context Clear** (Optional): `/clear` for next feature

**Performance Baseline**: 15-25 minutes per workflow

---

## Performance Optimization

**10 Phases Complete**:

- **Phase 4**: Haiku model for researcher (3-5 min saved)
- **Phase 5**: Prompt simplification (2-4 min saved)
- **Phase 6**: Profiling infrastructure (PerformanceTimer, JSON logging)
- **Phase 7**: Parallel validation (60% faster - 5 min → 2 min)
- **Phase 8**: Agent output cleanup (~2,900 tokens saved)
- **Phase 8.5**: Real-time performance analysis API
- **Phase 9**: Model downgrade strategy (investigative)
- **Phase 10**: Smart agent selection (95% faster for typos/docs)

**Cumulative Impact**:
- ~11,980 tokens saved per workflow
- 25-30% overall improvement from 28-44 min baseline
- 50-100+ skills supported without context bloat

**See**: [docs/PERFORMANCE.md](docs/PERFORMANCE.md) for complete benchmarks

---

## Security Architecture

**Multi-Layer Defense**:

1. **Native Tool Fast Path** (v4.1.0+): Built-in tools bypass validation
   - Native Claude Code tools (Read, Write, Bash, Task, etc.) skip all validation layers
   - Governed by settings.json permissions instead
   - Prevents permission prompts for standard tools

2. **MCP Security** (v3.37.0+): Permission-based validation
   - Path traversal prevention (CWE-22)
   - Command injection blocking (CWE-78)
   - SSRF prevention (CWE-918)

3. **Sandboxing** (v4.0.0+): Command classification
   - Safe commands auto-approved
   - Blocked patterns denied
   - Shell injection detection

4. **Auto-Approval** (v3.40.0+): Batch permission caching
   - Reduces prompts from 50+ to 8-10 (84% reduction)
   - 4-layer permission architecture

**See**:
- [docs/SANDBOXING.md](docs/SANDBOXING.md) - Complete sandboxing guide
- [docs/MCP-SECURITY.md](docs/MCP-SECURITY.md) - MCP security reference
- [docs/SECURITY.md](docs/SECURITY.md) - Security audit guide

---

## Configuration

**Key Configuration Files**:
- `.claude/PROJECT.md` - Strategic goals and constraints
- `.env` - Environment variables and feature flags
- `plugins/autonomous-dev/config/sandbox_policy.json` - Sandboxing rules
- `plugins/autonomous-dev/config/auto_approve_policy.json` - Auto-approval rules
- `plugins/autonomous-dev/config/test_routing_config.json` - Smart test routing rules: per-category tier enable/disable, marker mappings, always_smoke and docs_only_skip_all flags
- `~/.autonomous-dev/user_state.json` - User consent persistence

**Feature Flags**:
- `AUTO_GIT_ENABLED` - Enable automatic git operations
- `MCP_AUTO_APPROVE` - Enable auto-approval
- `SANDBOX_ENABLED` - Enable command sandboxing
- `ENABLE_PAUSE_CONTROLLER` - Enable human-in-the-loop
- `ENABLE_MEMORY_LAYER` - Enable cross-session memory

---

## Cross-References

**Related Documentation**:
- [docs/AGENTS.md](docs/AGENTS.md) - Complete agent reference

- [docs/LIBRARIES.md](docs/LIBRARIES.md) - Library API documentation
- [docs/HOOKS.md](docs/HOOKS.md) - Hook reference
- [docs/PERFORMANCE.md](docs/PERFORMANCE.md) - Performance benchmarks
- [docs/SECURITY.md](docs/SECURITY.md) - Security guide
