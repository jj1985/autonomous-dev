# autonomous-dev Plugin

**A Development Harness for Claude Code**

15 Agents | 17 Skills | 22 Hooks | 196 Libraries | 22 Commands

Deterministic enforcement, specialist agents, and alignment gates that wrap Claude Code with a full software development lifecycle.

---

## Quick Start

```bash
# Install
bash <(curl -sSL https://raw.githubusercontent.com/akaszubski/autonomous-dev/master/install.sh)

# Restart Claude Code (Cmd+Q / Ctrl+Q), wait 5 seconds, reopen

# Verify installation
/health-check

# Create PROJECT.md for goal alignment
/setup
```

---

## What You Get

### Acceptance-First Development Pipeline

One command triggers a complete quality workflow:

```bash
/implement "#72"              # From GitHub issue
/implement "Add user auth"    # From description
```

**The pipeline automatically:**
1. **Validates alignment** against PROJECT.md goals (blocks if misaligned)
2. **Researches patterns** in your codebase and web (parallel)
3. **Plans architecture** for the feature
4. **Writes acceptance tests** that define what "done" means
5. **Implements code + unit tests** to satisfy acceptance criteria
6. **Validates against spec** — spec-validator writes behavioral tests from criteria only, without seeing implementation (HARD GATE)
7. **Reviews code quality** + **audits security** + **updates docs** (parallel or ordered)
8. **Commits, pushes, closes issue** (consent-based)

**Result**: Production-ready code in 15-25 minutes.

### Pipeline Modes

```bash
/implement "#72"              # Full pipeline (default) — acceptance-first
/implement --light "#72"      # Light pipeline — docs/config/simple changes
/implement --tdd-first "#72"  # TDD-first — unit tests before implementation
/implement --fix "#72"        # Fix mode — minimal pipeline for test fixes
```

### Batch Processing

```bash
/implement --issues 72 73 74 75    # Multiple GitHub issues with worktree isolation
/implement --batch backlog.txt     # From a file (one feature per line)
/implement --resume <batch-id>     # Resume after context reset
```

---

## Installation

### One-Line Install (Recommended)

```bash
bash <(curl -sSL https://raw.githubusercontent.com/akaszubski/autonomous-dev/master/install.sh)
```

**What it installs:**
- Global infrastructure: `~/.claude/hooks/` (30 hooks), `~/.claude/lib/` (181 libraries), `~/.claude/settings.json`
- Project files: `.claude/commands/`, `.claude/agents/`, `.claude/skills/`
- Git hooks: Pre-commit validation, auto-formatting

**After installation:**
```bash
# Fully quit and restart Claude Code
# Press Cmd+Q (Mac) or Ctrl+Q (Windows/Linux), wait 5 seconds before reopening

# Verify
/health-check
```

### Manual Installation

```bash
# Clone repository
git clone https://github.com/akaszubski/autonomous-dev.git
cd autonomous-dev

# Run installation script
bash install.sh

# Restart Claude Code (Cmd+Q / Ctrl+Q)
```

### Update

```bash
/sync                  # Auto-detect context
/sync --github         # Fetch from GitHub
```

### Uninstallation

```bash
/sync --uninstall              # Preview what will be removed
/sync --uninstall --force      # Remove with backup
```

---

## Commands

### Implementation

```bash
/implement "#72"                    # Full pipeline (default)
/implement --light "#72"            # Light mode for docs/config
/implement --tdd-first "#72"        # Legacy TDD-first mode
/implement --fix "#72"              # Minimal fix pipeline
/implement --issues 72 73 74        # Batch from GitHub issues
/implement --batch features.txt     # Batch from file
/implement --resume <batch-id>      # Resume after crash/clear
```

### Project Management

```bash
/plan "..."              # 7-step planning workflow with adversarial plan-critic (--no-issues)
/status                  # View PROJECT.md goal progress
/align                   # Check alignment (--project, --docs, --retrofit)
/create-issue "..."      # Create GitHub issue with automated research (--quick)
/plan-to-issues          # Thorough-mode batch issue creation from plan output (--quick)
/health-check            # Verify plugin installation
/setup                   # Interactive PROJECT.md creation
```

### Quality & Analysis

```bash
/audit                   # Quality audit (--quick, --security, --docs, --code, --tests)
/refactor                # Code, docs, and test optimization (--tests, --docs, --code, --fix, --quick)
/sweep                   # Quick codebase hygiene (alias for /refactor --quick); --tests for test pruning
/advise                  # Critical thinking analysis — validates alignment, challenges assumptions
/improve                 # Automation health analysis (--auto-file to create GitHub issues)
/retrospective           # Session drift detection and alignment updates
/skill-eval              # Measure skill effectiveness via behavioral delta scoring (--quick, --skill, --update)
/autoresearch            # Autonomous experiment loop — hypothesize, modify, benchmark, commit or revert
```

### Other

```bash
/sync                    # Update plugin (--github, --env, --all, --uninstall)
/worktree                # Git worktrees (--list, --status, --merge, --discard)
/scaffold-genai-uat      # Scaffold LLM-as-judge tests into any repo
/mem-search              # Search persistent memory
```

---

## Architecture

### Three-Layer Harness

autonomous-dev enforces process through three layers, each addressing a different failure mode:

- **Hooks** (deterministic enforcement) — 27 hooks with JSON `{"decision": "block"}` hard gates. Run on every tool call, commit, and prompt. If the model tries to skip a step, it's physically blocked. Research-confirmed: prompt-level nudges produce unreliable compliance.

- **Agents** (adversarial evaluation) — 16 specialist agents, each spawned with fresh context and constrained tools. The implementer never reviews its own work. A separate reviewer and security-auditor evaluate it. A spec-validator writes behavioral tests from acceptance criteria without seeing the implementation. A plan-critic adversarially reviews plans before implementation begins.

- **Skills** (progressive context injection) — 19 domain knowledge packages injected only when relevant. Testing standards load during test writing. Security patterns load during security review. Prompt engineering patterns load when editing agent files. Prevents context bloat and drift.

### Component Overview

| Component | Count | Purpose |
|-----------|-------|---------|
| **Agents** | 16 | Specialist AI for each SDLC stage |
| **Skills** | 19 | Domain expertise (progressive disclosure) |
| **Hooks** | 27 | Deterministic enforcement and validation |
| **Libraries** | 180 | Python utilities (security, validation, automation) |
| **Commands** | 23 | Slash commands for workflows |

### Agent Specialization

**Model Tier Strategy (Cost-Optimized):**

| Tier | Model | Agents | Purpose |
|------|-------|--------|---------|
| Tier 1 | Haiku | researcher-local, test-coverage-auditor, issue-creator | Fast pattern matching |
| Tier 2 | Sonnet | researcher, reviewer, security-auditor, doc-master, continuous-improvement-analyst, retrospective-analyst, ui-tester, mobile-tester | Balanced reasoning |
| Tier 3 | Opus | planner, implementer, test-master, spec-validator, plan-critic | Deep reasoning |

### Hook Enforcement

**27 hooks enforce quality without manual intervention:**

| Hook Type | Trigger | What It Enforces |
|-----------|---------|-----------------|
| **PreToolUse** | Before tool execution | 6-layer enforcement: Sandbox, MCP Security, Agent Auth, Batch Permission, Pipeline Ordering Gate, Prompt Quality Gate. `plan_gate.py` blocks complex Write/Edit without validated plan. |
| **PrePromptSubmit** | Before user prompt | Workflow discipline; staged plan-exit 2-state machine (`plan_exited` → `critique_done`) requires plan-critic before non-question prompts |
| **PostToolUse** | After tool execution | Auto-format, auto-test, security scan, doc sync |
| **PreCommit** | Before git commit | Project alignment, orchestrator enforcement, TDD, session quality, agent completeness gate (per-issue in batch mode) |
| **SubagentStop / Stop** | After agent / session ends | Plan-exit stage advancement, conversation archival to SQLite index for long-term analytics |

### Testing: The Diamond Model

autonomous-dev uses a **diamond testing model** — not the traditional TDD pyramid. All 6 layers are implemented:

```
     /  Acceptance Criteria  \     Human-defined, LLM-as-judge evaluated
    / LLM-as-Judge Eval Layer \    52 GenAI test files, ~85% human agreement
   / Integration & Contract    \   Generated from acceptance criteria
   \ Property-Based Invariants /   13 Hypothesis test files
    \ Deterministic Unit Tests/    Regression locks, not specifications
     \  Type System / Lints  /     Hard floor, zero tolerance
```

**Key design decisions:**
- **Acceptance-first by default** — acceptance tests define "done" before implementation starts
- **Spec-blind validation** (HARD GATE) — spec-validator writes behavioral tests from criteria only, without seeing implementation
- **Unit tests are regression locks**, not specifications — agents game unit tests; they can't game acceptance criteria
- **Property-based invariants** catch bugs unit tests miss (+23-37% pass@1)
- **LLM-as-judge evaluation** validates semantic intent

See [Testing Strategy](../../docs/TESTING-STRATEGY.md) for the full 6-layer model with research citations.

---

## Configuration

### Environment Variables

Create `.env` file in your project root:

```bash
# Git Automation (default: enabled with consent)
AUTO_GIT_ENABLED=true      # Master switch for git automation
AUTO_GIT_PUSH=true         # Auto-push after commit
AUTO_GIT_PR=true           # Auto-create pull requests
AUTO_GIT_CLOSE_ISSUE=true  # Auto-close GitHub issues

# MCP Auto-Approval (default: disabled)
MCP_AUTO_APPROVE=true           # Auto-approve safe tool calls
SANDBOX_ENABLED=true            # Command classification and sandboxing
SANDBOX_PROFILE=development     # Options: development, testing, production

# Observability (default: minimal)
LOG_LEVEL=INFO                  # Options: DEBUG, INFO, WARNING, ERROR
```

### MCP Auto-Approval

**Impact**: Reduces permission prompts from 50+ to 8-10 (84% reduction)

**4-Layer Security Architecture:**
1. **Sandbox Enforcer**: Command classification (SAFE/BLOCKED/NEEDS_APPROVAL)
2. **MCP Security Validator**: Path traversal (CWE-22), injection (CWE-78), SSRF (CWE-918) prevention
3. **Agent Authorization**: Pipeline agent detection
4. **Batch Permission Approver**: Caches user consent for identical operations

---

## Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| Commands not appearing after install | Fully quit Claude Code (Cmd+Q / Ctrl+Q) and reopen |
| ModuleNotFoundError: autonomous_dev | Create symlink: `cd plugins && ln -s autonomous-dev autonomous_dev` |
| Context budget exceeded | Run `/clear` after each feature |
| Hooks not running | Check `~/.claude/settings.json` for hook configuration |

### Installation Verification

```bash
# Check what was installed
echo "Hooks: $(ls ~/.claude/hooks/*.py 2>/dev/null | wc -l)"        # Should be ~27
echo "Libs: $(ls ~/.claude/lib/*.py 2>/dev/null | wc -l)"           # Should be ~180
echo "Commands: $(ls .claude/commands/*.md 2>/dev/null | wc -l)"    # Should be ~23
echo "Agents: $(ls .claude/agents/*.md 2>/dev/null | wc -l)"        # Should be ~16

# Test health check
/health-check
```

### Pipeline Issues

**"/implement stops mid-way":**
1. Check for test failures (STEP 8 HARD GATE) — fix failing tests
2. Check for security issues — address vulnerabilities
3. Context may be full — run `/clear` and retry
4. Check agent output for specific errors

**"/implement --batch crashes":**
```bash
# Resume from where it stopped
/implement --resume <batch-id>

# Check batch state
cat .claude/batch_state.json
```

### Getting Help

1. **Run health check**: `/health-check` validates plugin integrity
2. **Check documentation**: See [full troubleshooting guide](docs/TROUBLESHOOTING.md)
3. **Search issues**: [GitHub Issues](https://github.com/akaszubski/autonomous-dev/issues)

---

## Best Practices

### Context Management

Run `/clear` after each feature to prevent context bloat:
```bash
/implement "#72"    # Feature 1
/clear
/implement "#73"    # Feature 2
/clear
```

Batch processing handles this automatically with worktree isolation and checkpoint/resume.

### Workflow Discipline

**Use `/implement` for all code changes.** Direct editing is only for:
- Documentation updates (.md files only)
- Config changes (.json, .yaml, .toml)
- Typo fixes (1-2 lines, no logic changes)

### PROJECT.md-First Development

Every `/implement` validates alignment against PROJECT.md:
- Does this feature align with **GOALS**?
- Is it within **SCOPE**?
- Does it violate **CONSTRAINTS**?
- Does it follow **ARCHITECTURE**?

---

## Documentation

| Guide | Description |
|-------|-------------|
| [CLAUDE.md](../../CLAUDE.md) | Project instructions and quick reference |
| [Architecture](../../docs/ARCHITECTURE-OVERVIEW.md) | Technical architecture deep-dive |
| [Planning Workflow](../../docs/PLANNING-WORKFLOW.md) | 7-step `/plan` + plan-critic adversarial review |
| [Prompt Engineering](../../docs/PROMPT-ENGINEERING.md) | Constraint budgets, register shifting, HARD GATE patterns |
| [Testing Strategy](../../docs/TESTING-STRATEGY.md) | Diamond testing model (6 layers) |
| [Agents](../../docs/AGENTS.md) | Agent pipeline and specialization (16 agents) |
| [Hooks](../../docs/HOOKS.md) | 30 active hooks reference |
| [Hook Registry](../../docs/HOOK-REGISTRY.md) | Sidecar metadata schema |
| [Libraries](../../docs/LIBRARIES.md) | 181 Python utilities |
| [Performance](../../docs/PERFORMANCE.md) | Benchmarks and optimization history |
| [Git Automation](../../docs/GIT-AUTOMATION.md) | Zero manual git operations |
| [Batch Processing](../../docs/BATCH-PROCESSING.md) | Multi-feature workflows with worktree isolation |
| [Workflow Discipline](../../docs/WORKFLOW-DISCIPLINE.md) | Two-tier ordering enforcement (coordinator + hook) |
| [Harness Evolution](../../docs/HARNESS-EVOLUTION.md) | How the harness has evolved across releases |
| [Security](../../docs/SECURITY.md) | Security model and hardening guide |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues and solutions |

---

## Requirements

- [Claude Code](https://claude.ai/code) 2.0+
- macOS or Linux
- Git
- Python 3.9+
- `gh` CLI (optional, for PR creation and issue management)

---

## Philosophy

### Automation > Reminders > Hope

Quality should be automatic, not optional:

- **Acceptance criteria** define "done" before implementation starts
- **Spec-blind validation** verifies behavior without seeing implementation
- **Security** is scanned on every feature
- **Documentation** stays in sync automatically
- **Git operations** are orchestrated end-to-end
- **Alignment** is validated against your stated intent

### Three-Layer Enforcement

| Layer | Mechanism | Purpose |
|-------|-----------|---------|
| **Hooks** | JSON `{"decision": "block"}` hard gates | Deterministic enforcement — can't be argued with |
| **Agents** | Adversarial evaluation (generator/evaluator) | Independent review — implementer never self-approves |
| **Skills** | Progressive context injection | Right knowledge at the right time — no context bloat |

You describe what you want. The harness enforces every step.

---

## License

MIT

---

<p align="center">
  <strong>Built for developers who ship.</strong>
</p>
