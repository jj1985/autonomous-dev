## [Unreleased]

### Added
- Property-based tests (Issue #509): `tests/property/` directory with three Hypothesis test modules covering `security_utils` path traversal and agent name invariants, `pipeline_state` state machine invariants (creation, step re-entry prevention, skippable step enforcement, round-trip persistence), and `tool_validator` classification invariants (blacklist, injection patterns, always-allowed tools). Tests auto-marked `property` + `slow` via `tests/conftest.py` directory marker. `property` marker registered in `pytest.ini`.
- Smart test routing (Issue #508): `/implement` STEP 5 now classifies changed files into categories (hook, lib, agent_prompt, command, config, skill, docs_only, install_sync) and runs only the relevant pytest marker tiers instead of the full suite. Docs-only changes skip tests entirely. Pass `--full-tests` to bypass routing and run the complete suite.
- `test_routing.py` library: `route_tests()` high-level API plus `classify_changes()`, `compute_marker_expression()`, and `get_skipped_tiers()` for per-category test tier selection.
- `step5_quality_gate.py` library: `run_quality_gate()` consolidates test execution (with smart routing), coverage regression check, and skip baseline enforcement into a single STEP 5 gate. `run_tests_routed()` delegates to `test_routing` when available and falls back to the full suite.
- `test_routing_config.json` config: routing rules per change category, tier-to-marker mappings, `always_smoke` and `docs_only_skip_all` flags — all user-tunable without code changes.
- `/refactor` command: unified code, docs, and test optimization with deeper analysis than `/sweep`. Three modes: `--tests` (Quality Diamond shape + waste detection), `--docs` (redundancy via SequenceMatcher), `--code` (dead code + unused lib detection). Supports `--fix` to apply fixes and `--quick` for the original sweep-style hygiene check.
- `refactor_analyzer.py` library: `RefactorAnalyzer` class orchestrating deep analysis across test shape, test waste, doc redundancy, dead code, and unused libraries. Composes `SweepAnalyzer` for quick-sweep mode.
- `ConfidenceLevel` enum (`HIGH`/`MEDIUM`/`LOW`) added to `refactor_analyzer.py`; `RefactorFinding` now carries a `confidence` field (default `HIGH`) so callers can filter findings by reliability.
- `/refactor --fix` now applies confidence-level gating: HIGH-confidence findings are passed to agents for automated fix, MEDIUM-confidence findings are surfaced as a "Manual Review Recommended" list (not auto-fixed), and LOW-confidence findings are excluded from `--fix` output entirely.
- Dead code and unused library detection now use word-boundary regex (`\b<name>\b`) to avoid false positives from partial name matches.
- Unused library detection now scans `.md` and `.sh` files in addition to `.py` files, reducing false positives where a lib is only referenced in documentation or shell scripts.
- `genai_refactor_analyzer.py` library: `GenAIRefactorAnalyzer` wraps `RefactorAnalyzer` with hybrid static-candidate + LLM-semantic analysis. Three passes: (1) doc-code drift via `covers:` frontmatter with Haiku contradiction check and Sonnet escalation for HIGH findings, (2) hollow test detection pairing `test_foo.py` with `foo.py`, (3) dead code verification with dynamic dispatch context and confidence threshold (≥0.7). SHA-256 content hash caching at `.claude/cache/refactor/` prevents redundant API calls. (Issue #515)
- `/refactor --deep` flag: enables `GenAIRefactorAnalyzer` for semantic analysis (auto-enabled when `ANTHROPIC_API_KEY` is set and `--quick` is not). Findings prefixed with `[genai]` indicate higher-confidence semantic-level issues beyond structural detection.
- `/refactor --issues` flag: pipes findings into GitHub issues via `gh issue create` — HIGH/CRITICAL findings get individual issues, LOW/MEDIUM findings are aggregated into a single sweep issue.
- `/refactor --batch` flag: submits GenAI analysis via Anthropic Batch API for 50% cost reduction with async results.
- 5 new GenAI prompts added to `genai_prompts.py`: `DOC_CODE_DRIFT_PROMPT`, `HOLLOW_TEST_PROMPT`, `DEAD_CODE_VERIFY_PROMPT`, `REFACTOR_ESCALATION_PROMPT`, `REFACTOR_BATCH_SYSTEM_PROMPT` — structured prompts for each semantic analysis pass.

### Changed
- `/sweep` is now an alias for `/refactor --quick` instead of running independent analysis logic. Behavior is preserved; all hygiene sweep work is delegated to `RefactorAnalyzer.quick_sweep()`.

- `/implement` now writes `explicitly_invoked: true` flag to the pipeline state file (`/tmp/implement_pipeline_state.json`) on startup, enabling `unified_pre_tool.py` to hard-block coordinator code writes during active sessions regardless of `ENFORCEMENT_LEVEL` (Issue #528).

### Changed
- `unified_pre_tool.py` Agent Auth layer (Layer 2) now detects `explicitly_invoked` flag and denies Write/Edit/Bash to code files when the coordinator attempts to bypass pipeline agents during an active `/implement` session. Config files and docs remain exempt.
- Pipeline authorized agents (`PIPELINE_AGENTS`) updated to `implementer`, `test-master`, `doc-master` — removed legacy entries `brownfield-analyzer`, `setup-wizard`, `project-bootstrapper` that no longer exist.

### Fixed
- `RefactorAnalyzer` no longer scans `.worktrees/` or `.claude/` directories, which caused O(n²) timeout on large repos with multiple worktrees (Issue #514). Added `DEFAULT_EXCLUDE_DIRS` class constant (covers version control, caches, worktrees, session logs, archives) and `_should_skip_path()` helper used by all `rglob` traversals. The `__init__` signature now accepts an optional `exclude_dirs` parameter to override the defaults.

## [3.46.0] - 2026-01-09
### Fixed
- Fix doc-master auto-apply (#204)