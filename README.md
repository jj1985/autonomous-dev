# autonomous-dev — A Development Harness for Claude Code

![Version](https://img.shields.io/badge/version-3.51.0-blue)

**A harness that wraps Claude Code with enforcement, specialist agents, and alignment gates to deliver consistent, production-grade software engineering outcomes.**

A *harness* is the software and structure that wraps an AI model to keep it on track — the prompts, tools, feedback loops, constraints, and validation that turn a capable but undisciplined model into a reliable system. Without a harness, the model is a wild horse with raw power but no direction. With one, that power is controlled, directed, and accountable.

---

## What Is This?

**The problem**: Claude Code is brilliant at execution but unreliable at process. It skips tests, declares "good enough" on failing code, bypasses security reviews, and drifts from your project's intent. Not out of malice — it's trained to complete tasks, not follow engineering discipline. Prompt-level instructions ("please run tests") get ignored under context pressure.

**The solution**: autonomous-dev is a harness that enforces the full software development lifecycle:

1. **You define your project** in a file called PROJECT.md - your goals, what's in/out of scope, constraints, architecture
2. **You track work in GitHub Issues** - each feature or bug is an issue
3. **You run one command** - `/implement "#72"`
4. **Claude executes a full development pipeline** - research, planning, acceptance tests, implementation, code review, security scan, documentation
5. **Claude stays aligned** - if a feature doesn't fit your PROJECT.md scope, it's blocked before any code is written

**In short**: You define the rules once. The harness enforces them for every feature.

---

## What Does It Actually Do?

When you type `/implement "#72"`, Claude coordinates specialist agents through an 8-step pipeline:

| Step | Agent | What It Does |
|------|-------|--------------|
| 1 | **alignment check** | Checks if the feature fits your PROJECT.md goals and scope. Blocks if it doesn't. |
| 2 | **researcher** (x2) | Searches codebase + web for patterns, best practices, existing solutions |
| 3 | **planner** | Designs the architecture and creates a file-by-file implementation plan |
| 4 | **acceptance tests** | Writes acceptance tests that define what "done" means |
| 5 | **implementer** | Writes code + unit tests to make the acceptance tests pass |
| 6 | **reviewer** | Reviews code quality, checks patterns, flags issues |
| 7 | **security-auditor** | Scans for vulnerabilities (OWASP top 10) |
| 8 | **doc-master** | Updates documentation to match the new code |

After all agents complete:
- Code is committed with a descriptive message
- Changes are pushed to your branch
- The GitHub issue is closed with a summary

**One command. Full software development lifecycle. Aligned to your project.**

---

## Why Use This?

**Without a harness**:
- You ask Claude to build a feature
- Claude makes assumptions about your architecture
- It skips tests when context gets long (context anxiety)
- It approves its own work as "good enough" (poor self-evaluation)
- You review the code, find issues, ask for fixes
- Repeat until it's acceptable
- Hope you didn't introduce security issues

**With autonomous-dev**:
- You define your project once (PROJECT.md)
- You create a GitHub issue for each feature
- You run `/implement "#X"`
- The harness enforces every step — research, planning, testing, implementation, adversarial review, security audit, documentation
- You review a complete, tested, documented, security-scanned result

**The difference**: Claude stops guessing. The harness keeps it honest.

### Three-Layer Harness Architecture

autonomous-dev enforces process through three layers, each addressing a different failure mode:

- **Hooks** (deterministic enforcement) — Run on every tool call, commit, and prompt. Hard gates that can't be argued with: tests must pass with 0 failures before code review starts, no stubs or placeholders allowed, security scan is mandatory, documentation must stay in sync. These are the harness equivalent of guardrails — if the model tries to skip a step, it's physically blocked.

- **Agents** (adversarial evaluation) — Each pipeline step is handled by a specialist agent with a specific job and constrained tools. Critically, the implementer never reviews its own work — a separate reviewer agent with a skeptical mandate evaluates it. This follows the generator/evaluator pattern: the tension between agents improves quality, just like a GAN network. No single agent can skip steps or self-approve.

- **Skills** (progressive context injection) — Instead of stuffing the context window with every rule upfront (which causes context anxiety and drift), skills inject domain knowledge only when relevant. Testing standards load during test writing. Security patterns load during security review. This keeps Claude focused within its current step.

**The result**: Every feature goes through every step. Not because Claude remembers to, but because the harness won't let it skip.

### The 12 Elements of Harness Engineering

The core insight of harness engineering: reliability in multi-step AI workflows is difficult because failures compound. A 10-step process with 90% accuracy per step fails over 60% of the time. "Agent skills" that are just prompts or markdown files — where you *hope* the AI follows instructions — lack the dependability required for production work.

The solution is **deterministic rails**: a software layer that gates and validates every stage. autonomous-dev implements all 12 elements of this framework:

| # | Element | How autonomous-dev implements it |
|---|---------|----------------------------------|
| 1 | **State Machine** | `pipeline_state.py` — 13-phase state machine with `Step` enum, `advance()`/`complete_step()` API, JSON-persisted state |
| 2 | **Validation Loops** | STEP 8 HARD GATE — runs pytest, loops until 0 failures/0 errors. Anti-stubbing gate blocks `raise NotImplementedError()` shortcuts |
| 3 | **Isolated Sub-Agents** | 12 specialist agents, each spawned with fresh context and constrained tools. Model selection per agent (Haiku/Sonnet/Opus) |
| 4 | **Virtual File System** | Git worktree isolation for batch mode. `checkpoint.py` + `artifacts.py` persist outputs to `.claude/artifacts/` per phase |
| 5 | **Human-in-the-Loop** | Plan mode (STEP 5) requires user approval before implementation. `pause_controller.py` for explicit gates |
| 6 | **Hook Enforcement** | 27 hooks with JSON `{"decision": "block"}` hard gates — not prompt-level nudges. Research-confirmed: nudges produce unreliable compliance |
| 7 | **State Persistence** | `CheckpointManager` for resume after failure. `batch_state_manager.py` for multi-feature recovery. `/implement --resume` |
| 8 | **Context Management** | Progressive skill injection loads domain knowledge per-step. `/clear` between features. Agent isolation prevents context rot |
| 9 | **Deterministic Ordering** | `agent_ordering_gate.py` enforces pipeline sequence. "You MUST NOT run STEP 10 before STEP 8 test gate passes" |
| 10 | **Output Validation** | Parallel reviewer + security-auditor in STEP 10. `genai_validate.py` for LLM-as-judge tests. `completion_verifier.py` |
| 11 | **Observability** | `session_activity_logger.py`, `pipeline_timing_analyzer.py`, `token_tracker.py`. Structured JSONL to `.claude/logs/activity/` |
| 12 | **Error Recovery** | `failure_analyzer.py`, `batch_retry_manager.py`, `stuck_detector.py`, `qa_self_healer.py`. Automatic retry with consent |

---

## What's PROJECT.md?

A simple markdown file that defines your project. Example:

```markdown
# PROJECT.md

## GOALS
- Build a REST API for user management
- Achieve 80% test coverage
- Ship MVP by end of Q1

## SCOPE
IN: User CRUD, authentication, password reset
OUT: Admin dashboard, analytics, billing

## CONSTRAINTS
- Python 3.11+ with FastAPI
- PostgreSQL database
- JWT authentication (no sessions)
- All endpoints must have rate limiting

## ARCHITECTURE
- src/api/ - FastAPI route handlers
- src/models/ - SQLAlchemy models
- src/services/ - Business logic
- tests/ - Pytest test suite
```

When you run `/implement "Add user registration"`:
- Allowed - user registration is IN scope
- Claude follows your FastAPI + PostgreSQL + JWT constraints
- Tests go in `tests/`, code follows your architecture

When you run `/implement "Add analytics dashboard"`:
- Blocked - analytics is OUT of scope
- No code written, no time wasted
- You're asked to either change the request or update PROJECT.md

**This is how Claude stays aligned** - it reads PROJECT.md before every feature.

---

## Install

### Prerequisites

| Requirement | Install Command |
|-------------|-----------------|
| **Claude Code 2.0+** | [Download](https://claude.ai/download) |
| **Python 3.9+** | `python3 --version` to verify |
| **gh CLI** (GitHub) | `brew install gh && gh auth login` |

### One-Line Install

```bash
bash <(curl -sSL https://raw.githubusercontent.com/akaszubski/autonomous-dev/master/install.sh)
```

Then **fully quit Claude Code** (Cmd+Q on Mac, Ctrl+Q on Windows/Linux) and reopen it.

### Set Up Your Project

**Open your project folder in terminal**, then start Claude Code:
```bash
cd /path/to/your/project
claude
```

Run the setup wizard:
```
/setup
```

This will walk you through creating PROJECT.md and configuring the plugin for your project.

For existing projects, use:
```
/align --retrofit
```

### Update

```bash
/sync
```

### Uninstall

```bash
/sync --uninstall
```

---

## Usage

### Single Feature

```bash
/implement "#72"              # From GitHub issue
/implement "Add user auth"    # From description
```

### Pipeline Modes

```bash
/implement "#72"              # Full pipeline (default) - 7 agents, acceptance-first
/implement --light "#72"      # Light pipeline - docs/config/simple changes
/implement --tdd-first "#72"  # TDD-first - unit tests before implementation
/implement --fix "#72"        # Fix mode - minimal pipeline for test fixes
```

### Batch Processing

```bash
/implement --issues 72 73 74 75    # Multiple GitHub issues with worktree isolation
/implement --batch backlog.txt     # From a file (one feature per line)
/implement --resume <batch-id>     # Resume after context reset
```

### Project Management

```bash
/status                  # View PROJECT.md goal progress
/align                   # Check alignment (--project, --docs, --retrofit)
/create-issue "..."      # Create GitHub issue with automated research
/plan-to-issues          # Batch-convert plan mode output into GitHub issues
/health-check            # Verify plugin installation
```

### Quality & Analysis

```bash
/refactor                # Code, docs, and test optimization (--tests, --docs, --code, --fix)
/sweep                   # Quick codebase hygiene (alias for /refactor --quick); --tests for AST-based test pruning analysis
/audit                   # Quality audit (--quick, --security, --docs, --code, --tests)
/skill-eval              # Measure skill effectiveness via behavioral delta scoring (--quick, --skill, --update)
/advise                  # Critical thinking analysis
/improve                 # Automation health analysis
/retrospective           # Session drift detection and alignment updates
```

### Other Commands

```bash
/sync                    # Update plugin (--github, --env, --marketplace, --all)
/worktree                # Git worktrees (--list, --status, --merge, --discard)
/scaffold-genai-uat      # Scaffold LLM-as-judge tests into any repo
/mem-search              # Search claude-mem persistent memory
```

---

## How the Harness Works

### Generator / Evaluator Pipeline

Inspired by the adversarial evaluation pattern (generator creates, evaluator judges), every `/implement` runs this pipeline:

```
/implement "feature"
     |
PROJECT.md Alignment Check (blocks if misaligned)
     |
+------------------+------------------+
| Research-Local   | Research-Web     |  <- Parallel research
| (Haiku)          | (Sonnet)         |
+------------------+------------------+
     |
Planning (Opus)
     |
Acceptance Tests (Coordinator)
     |
Implementation (Opus) -> HARD GATE: 0 test failures
     |                 -> HARD GATE: No stubs/placeholders
     |                 -> HARD GATE: Hook registration verified
     |
+----------+------------+-----------+
| Review   | Security   | Docs      |  <- Ordered validation
| (Sonnet) | (Sonnet)   | (Sonnet)  |
+----------+------------+-----------+
     |
Git Operations (commit, push, close issue)
     |
Continuous Improvement (background analysis)
```

### PROJECT.md Alignment

Features validate against your PROJECT.md before work starts. If you request something OUT of scope, it's blocked - not implemented wrong.

### Context Management

As the context window fills up, models exhibit *context anxiety* — they rush through steps, declare things done prematurely, and degrade output quality. autonomous-dev handles this with context resets between features:

1. Each feature uses ~25-35K tokens
2. After 4-5 features, run `/clear` to reset context
3. Run `/implement --resume <batch-id>` to continue from where you left off

Batch processing handles this automatically with worktree isolation and checkpoint/resume.

---

## What You Get

| Component | Count | Purpose |
|-----------|-------|---------|
| Commands | 20 | Slash commands for workflows |
| Agents | 12 | Specialized AI for each SDLC stage |
| Skills | 17 | Domain knowledge (progressive disclosure) |
| Hooks | 25 | Automatic validation and enforcement |
| Libraries | 191 | Python utilities |

---

## Documentation

### Core Concepts
- [Architecture](docs/ARCHITECTURE-OVERVIEW.md) - Three-layer system (hooks + agents + continuous improvement)
- [Maintaining Philosophy](docs/MAINTAINING-PHILOSOPHY.md) - Why alignment-first works

### Workflows
- [Batch Processing](docs/BATCH-PROCESSING.md) - Multi-feature workflows
- [Git Automation](docs/GIT-AUTOMATION.md) - Auto-commit, push, issue close
- [Workflow Discipline](docs/WORKFLOW-DISCIPLINE.md) - Pipeline enforcement

### Reference
- [Commands](plugins/autonomous-dev/commands/) - All 21 commands
- [Hooks](docs/HOOKS.md) - 27 active hooks
- [Libraries](docs/LIBRARIES.md) - 191 Python utilities
- [Testing Strategy](docs/TESTING-STRATEGY.md) - Diamond testing model

### Troubleshooting
- [Troubleshooting Guide](plugins/autonomous-dev/docs/TROUBLESHOOTING.md) - Common issues

---

## Quick Reference

```bash
# Install
bash <(curl -sSL https://raw.githubusercontent.com/akaszubski/autonomous-dev/master/install.sh)
# Restart Claude Code (Cmd+Q / Ctrl+Q)

# Daily workflow
/implement "#72"                    # Single feature
/implement --issues 1 2 3           # Multiple features
/implement --fix "#99"              # Fix a failing test
/clear                              # Reset context between features

# Check status
/health-check                       # Verify installation
/status                             # View alignment

# Update
/sync                               # Get latest version
```

---

## Support

- **Issues**: [github.com/akaszubski/autonomous-dev/issues](https://github.com/akaszubski/autonomous-dev/issues)
- **Changelog**: [CHANGELOG.md](CHANGELOG.md)

---

## License

MIT License
