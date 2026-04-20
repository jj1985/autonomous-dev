# GitHub Labels & Finding Tags

Two parallel taxonomies are used across the repo: GitHub issue labels (applied by humans and the CI analyst) and inline finding tags (embedded in issue bodies and session logs).

---

## GitHub Issue Labels

Applied via `gh issue create --label <name>` or the GitHub UI.

### Lifecycle & Intent

| Label | Meaning |
|-------|---------|
| `bug` | Something isn't working (behavior doesn't match spec or docs) |
| `enhancement` | New feature or capability request |
| `documentation` | Docs additions/corrections — no code change required |
| `question` | Request for clarification; may not result in code change |
| `duplicate` | This issue already exists — link to original and close |
| `invalid` | Not actionable (not a real bug, out of scope, unclear) |
| `wontfix` | Intentionally not addressing — keep closed for history |
| `good first issue` | Small, well-scoped; suitable for a first-time contributor |
| `help wanted` | Owner can't pick this up — external attention welcome |

### Priority Tiers

| Label | Priority | When used |
|-------|----------|-----------|
| `Tier-1` | Critical / Foundation | Security, data loss, pipeline blocking |
| `Tier-2` | Important / Automation | Regressions, significant friction, measurable cost |
| `Tier-3` | Polish / Future | Minor improvements, nice-to-haves |
| `validate-need` | Validate before implementing | Unclear if we actually need this — research first |

### Domain

| Label | Area |
|-------|------|
| `security` | Security and enforcement hardening |
| `pipeline` | Pipeline completeness and reliability (steps, gates, ordering) |
| `performance` | Pipeline and runtime performance (latency, token cost) |

### CI Analyst Labels (auto-applied)

| Label | Applied by | Meaning |
|-------|------------|---------|
| `auto-improvement` | `continuous-improvement-analyst` | Finding from post-session analysis |
| `continuous-improvement` | `/improve` command | General CI analyst output (may overlap with auto-improvement) |
| `trends` | `/improve --trends` | Aggregate pattern across many sessions (fires every ~10 issues as a rollup) |
| `root-cause` | Human (after triage) | Consolidated issue that groups several auto-improvement reports under a single root cause |

### Application & Triage Flow

1. CI analyst files `auto-improvement` issues with a specific `[TAG]` in the title (see inline tags below).
2. Weekly triage rolls same-root-cause issues into one `root-cause` issue.
3. Priority tier is assigned on triage: `Tier-1` if blocking or security-adjacent, else `Tier-2` or `Tier-3`.
4. `trends` issues are not triaged individually — they show aggregate patterns.

---

## Inline Finding Tags

These appear in the `title` of auto-filed issues and in session logs. They're produced by the `continuous-improvement-analyst` agent — see `plugins/autonomous-dev/agents/continuous-improvement-analyst.md` for the full check list.

| Tag | What it flags | Example title |
|-----|---------------|---------------|
| `[INCOMPLETE]` | Pipeline skipped a required agent for its mode | `[INCOMPLETE] spec-validator absent in --fix mode (Issue #877)` |
| `[BYPASS]` | A HARD GATE was circumvented | `[BYPASS] SKIP_AGENT_COMPLETENESS_GATE=1 used in commit abc123` |
| `[ORDERING]` | Agent dispatched out of pipeline sequence | `[ORDERING] reviewer ran before test gate completed` |
| `[HOOK-REGRESSION]` | Hook registered behavior differs from prior run | `[HOOK-REGRESSION] auto_test.py failed to fire on Python edits` |
| `[GAMING]` | Test softening, skip inflation, coverage narrowing | `[GAMING] 6 tests added @pytest.mark.skip in session 9d5b5808` |
| `[TEST-IMBALANCE]` | Test tier distribution drifted from expected | `[TEST-IMBALANCE] T0 tests added without T2/T3 coverage` |
| `[TEST-PRUNING]` | Tests look orphaned, archived, or redundant | `[TEST-PRUNING] test_foo.py references removed function bar()` |
| `[DOC-VERDICT-MISSING]` | `doc-master` agent produced no verdict after retry | `[DOC-VERDICT-MISSING] background agent exited empty 3 times` |
| `[FIDELITY]` | Coordinator truncated agent output before passing downstream | `[FIDELITY] implementer output 12K words → reviewer got 2K words` |
| `[CI]` | Continuous-improvement infrastructure issue (meta) | `[CI] CLAUDE_SESSION_ID not propagated to subshells` |

### Tag Lifecycle

Tags are part of the issue title so they remain searchable even if the `auto-improvement` label is removed during triage. Commands for finding them:

```bash
# Count occurrences of each finding type
gh issue list --repo akaszubski/autonomous-dev --label auto-improvement --limit 100 \
  --json title --jq '.[] | .title' | grep -oE '\[[A-Z-]+\]' | sort | uniq -c | sort -rn

# List all open BYPASS findings
gh issue list --repo akaszubski/autonomous-dev --state open \
  --search 'in:title "[BYPASS]"'

# Oldest-lived issues (most systemic)
gh issue list --repo akaszubski/autonomous-dev --label auto-improvement --state open \
  --json number,title,createdAt --jq 'sort_by(.createdAt) | .[0:5]'
```

---

## Repository-Specific Label Variants

The `continuous-improvement-analyst` can file to:

- `akaszubski/autonomous-dev` for **framework findings** (the harness itself)
- The **active consumer repo** for **app-code findings** (bugs in the project being built with autonomous-dev)

This separation is intentional — the framework repo tracks its own quality, consumer repos track theirs.

---

## Related

- [EVALUATION.md](EVALUATION.md) — `/improve` workflow that files these issues
- [AGENTS.md](AGENTS.md) — `continuous-improvement-analyst` agent spec
- [PIPELINE-MODES.md](PIPELINE-MODES.md) — when the CI analyst fires in each pipeline mode (STEP 15 full; post-batch for `--batch`)
