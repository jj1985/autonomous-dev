## [Unreleased]

### Added
- Property-based tests (Issue #509): `tests/property/` directory with three Hypothesis test modules covering `security_utils` path traversal and agent name invariants, `pipeline_state` state machine invariants (creation, step re-entry prevention, skippable step enforcement, round-trip persistence), and `tool_validator` classification invariants (blacklist, injection patterns, always-allowed tools). Tests auto-marked `property` + `slow` via `tests/conftest.py` directory marker. `property` marker registered in `pytest.ini`.
- Smart test routing (Issue #508): `/implement` STEP 5 now classifies changed files into categories (hook, lib, agent_prompt, command, config, skill, docs_only, install_sync) and runs only the relevant pytest marker tiers instead of the full suite. Docs-only changes skip tests entirely. Pass `--full-tests` to bypass routing and run the complete suite.
- `test_routing.py` library: `route_tests()` high-level API plus `classify_changes()`, `compute_marker_expression()`, and `get_skipped_tiers()` for per-category test tier selection.
- `step5_quality_gate.py` library: `run_quality_gate()` consolidates test execution (with smart routing), coverage regression check, and skip baseline enforcement into a single STEP 5 gate. `run_tests_routed()` delegates to `test_routing` when available and falls back to the full suite.
- `test_routing_config.json` config: routing rules per change category, tier-to-marker mappings, `always_smoke` and `docs_only_skip_all` flags — all user-tunable without code changes.
- `/refactor` command: unified code, docs, and test optimization with deeper analysis than `/sweep`. Three modes: `--tests` (Quality Diamond shape + waste detection), `--docs` (redundancy via SequenceMatcher), `--code` (dead code + unused lib detection). Supports `--fix` to apply fixes and `--quick` for the original sweep-style hygiene check.
- `refactor_analyzer.py` library: `RefactorAnalyzer` class orchestrating deep analysis across test shape, test waste, doc redundancy, dead code, and unused libraries. Composes `SweepAnalyzer` for quick-sweep mode.

### Changed
- `/sweep` is now an alias for `/refactor --quick` instead of running independent analysis logic. Behavior is preserved; all hygiene sweep work is delegated to `RefactorAnalyzer.quick_sweep()`.

### Fixed
- `RefactorAnalyzer` no longer scans `.worktrees/` or `.claude/` directories, which caused O(n²) timeout on large repos with multiple worktrees (Issue #514). Added `DEFAULT_EXCLUDE_DIRS` class constant (covers version control, caches, worktrees, session logs, archives) and `_should_skip_path()` helper used by all `rglob` traversals. The `__init__` signature now accepts an optional `exclude_dirs` parameter to override the defaults.

## [3.46.0] - 2026-01-09
### Fixed
- Fix doc-master auto-apply (#204)