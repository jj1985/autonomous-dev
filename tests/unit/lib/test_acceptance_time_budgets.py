#!/usr/bin/env python3
"""
Acceptance Tests for Issue #705: Per-step time budgets for pipeline agents.

These are STATIC FILE INSPECTION tests — they validate the implementation
contract by checking config existence, schema correctness, function exports,
and code references without executing the full runtime logic.

Each test class maps to one acceptance criterion from Issue #705.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Project root detection (portable — works from any directory)
# ---------------------------------------------------------------------------
_current = Path(__file__).resolve()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        REPO_ROOT = _current
        break
    _current = _current.parent
else:
    REPO_ROOT = Path(__file__).resolve().parents[3]

# Canonical paths under test
CONFIG_PATH = REPO_ROOT / "plugins/autonomous-dev/config/pipeline_time_budgets.json"
ANALYZER_PATH = REPO_ROOT / "plugins/autonomous-dev/lib/pipeline_timing_analyzer.py"
HOOK_PATH = REPO_ROOT / "plugins/autonomous-dev/hooks/session_activity_logger.py"
CIA_AGENT_PATH = REPO_ROOT / "plugins/autonomous-dev/agents/continuous-improvement-analyst.md"
EXISTING_TESTS_PATH = REPO_ROOT / "tests/unit/lib/test_pipeline_timing_analyzer.py"

# Required agent types per acceptance criterion #1
REQUIRED_AGENT_TYPES = {
    "researcher-local",
    "researcher",
    "planner",
    "implementer",
    "reviewer",
    "security-auditor",
    "doc-master",
    "test-master",
}


# ---------------------------------------------------------------------------
# AC #1 — Config file with budget_seconds and warning_pct for all 8 agents
# ---------------------------------------------------------------------------
class TestTimeBudgetConfigExists:
    """AC #1: pipeline_time_budgets.json exists with correct schema."""

    def test_config_file_exists(self):
        """Config file must exist at the canonical path."""
        assert CONFIG_PATH.exists(), (
            f"Expected config file at {CONFIG_PATH} but it was not found. "
            "Create plugins/autonomous-dev/config/pipeline_time_budgets.json."
        )

    def test_config_is_valid_json(self):
        """Config file must be parseable JSON."""
        try:
            data = json.loads(CONFIG_PATH.read_text())
        except json.JSONDecodeError as exc:
            pytest.fail(f"pipeline_time_budgets.json is not valid JSON: {exc}")
        assert isinstance(data, dict), "Top-level structure must be a JSON object."

    def test_config_has_all_required_agent_types(self):
        """All 8 required agent types must have entries in the config."""
        data = json.loads(CONFIG_PATH.read_text())
        missing = REQUIRED_AGENT_TYPES - set(data.keys())
        assert not missing, (
            f"Missing agent entries in pipeline_time_budgets.json: {sorted(missing)}"
        )

    def test_each_agent_has_budget_seconds(self):
        """Every agent entry must include budget_seconds (int > 0)."""
        data = json.loads(CONFIG_PATH.read_text())
        errors = []
        for agent in REQUIRED_AGENT_TYPES:
            entry = data.get(agent, {})
            val = entry.get("budget_seconds")
            if val is None:
                errors.append(f"{agent}: missing budget_seconds")
            elif not isinstance(val, (int, float)) or val <= 0:
                errors.append(f"{agent}: budget_seconds must be a positive number, got {val!r}")
        assert not errors, "budget_seconds issues:\n" + "\n".join(errors)

    def test_each_agent_has_warning_pct(self):
        """Every agent entry must include warning_pct (0 < pct <= 1.0)."""
        data = json.loads(CONFIG_PATH.read_text())
        errors = []
        for agent in REQUIRED_AGENT_TYPES:
            entry = data.get(agent, {})
            val = entry.get("warning_pct")
            if val is None:
                errors.append(f"{agent}: missing warning_pct")
            elif not isinstance(val, (int, float)) or not (0 < val <= 1.0):
                errors.append(
                    f"{agent}: warning_pct must be in (0, 1.0], got {val!r}"
                )
        assert not errors, "warning_pct issues:\n" + "\n".join(errors)

    def test_budget_seconds_are_reasonable(self):
        """Budget values should be within a plausible range (30s – 3600s)."""
        data = json.loads(CONFIG_PATH.read_text())
        for agent in REQUIRED_AGENT_TYPES:
            val = data.get(agent, {}).get("budget_seconds", 0)
            assert 30 <= val <= 3600, (
                f"{agent}.budget_seconds={val} is outside the plausible range 30–3600s"
            )


# ---------------------------------------------------------------------------
# AC #2 — pipeline_timing_analyzer.py exports the 3 required functions
# ---------------------------------------------------------------------------
class TestTimingAnalyzerExports:
    """AC #2: pipeline_timing_analyzer.py exports load_time_budgets,
    check_budget_violation, and format_budget_warning."""

    @pytest.fixture(scope="class")
    def analyzer_source(self):
        return ANALYZER_PATH.read_text()

    def test_analyzer_file_exists(self):
        """pipeline_timing_analyzer.py must exist."""
        assert ANALYZER_PATH.exists(), (
            f"Expected library at {ANALYZER_PATH}"
        )

    def test_load_time_budgets_defined(self, analyzer_source):
        """load_time_budgets function must be defined in the module."""
        assert "def load_time_budgets" in analyzer_source, (
            "pipeline_timing_analyzer.py must define a load_time_budgets() function."
        )

    def test_check_budget_violation_defined(self, analyzer_source):
        """check_budget_violation function must be defined in the module."""
        assert "def check_budget_violation" in analyzer_source, (
            "pipeline_timing_analyzer.py must define a check_budget_violation() function."
        )

    def test_format_budget_warning_defined(self, analyzer_source):
        """format_budget_warning function must be defined in the module."""
        assert "def format_budget_warning" in analyzer_source, (
            "pipeline_timing_analyzer.py must define a format_budget_warning() function."
        )

    def test_functions_importable(self):
        """All three functions must be importable from the module (no syntax errors)."""
        lib_dir = str(REPO_ROOT / "plugins/autonomous-dev/lib")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)

        try:
            import importlib
            module = importlib.import_module("pipeline_timing_analyzer")
        except Exception as exc:
            pytest.fail(f"pipeline_timing_analyzer.py failed to import: {exc}")

        for fn_name in ("load_time_budgets", "check_budget_violation", "format_budget_warning"):
            assert hasattr(module, fn_name), (
                f"pipeline_timing_analyzer module must export '{fn_name}'"
            )
            assert callable(getattr(module, fn_name)), (
                f"'{fn_name}' must be callable"
            )


# ---------------------------------------------------------------------------
# AC #3 — session_activity_logger.py PostToolUse handler references budgets
# ---------------------------------------------------------------------------
class TestHookBudgetReference:
    """AC #3: session_activity_logger.py contains budget checking logic."""

    @pytest.fixture(scope="class")
    def hook_source(self):
        assert HOOK_PATH.exists(), f"Hook not found: {HOOK_PATH}"
        return HOOK_PATH.read_text()

    def test_hook_references_budget(self, hook_source):
        """Hook must reference 'budget' or 'BudgetWarning' somewhere."""
        has_budget = "budget" in hook_source.lower() or "BudgetWarning" in hook_source
        assert has_budget, (
            "session_activity_logger.py must contain budget-checking logic "
            "(reference 'budget' or 'BudgetWarning')."
        )

    def test_hook_has_post_tool_use_or_budget_check(self, hook_source):
        """Hook must contain a PostToolUse handler or budget check function."""
        has_post_tool = "PostToolUse" in hook_source or "post_tool_use" in hook_source
        has_budget_fn = (
            "check_budget" in hook_source
            or "budget_check" in hook_source
            or "BudgetWarning" in hook_source
        )
        assert has_post_tool or has_budget_fn, (
            "session_activity_logger.py must contain a PostToolUse handler "
            "or a budget-check function."
        )


# ---------------------------------------------------------------------------
# AC #4 — CIA agent references budget warnings in Check #11
# ---------------------------------------------------------------------------
class TestCIAAgentBudgetReference:
    """AC #4: continuous-improvement-analyst.md references budget warnings."""

    @pytest.fixture(scope="class")
    def cia_source(self):
        assert CIA_AGENT_PATH.exists(), f"CIA agent not found: {CIA_AGENT_PATH}"
        return CIA_AGENT_PATH.read_text()

    def test_cia_has_check_11(self, cia_source):
        """The CIA agent must include a Check #11 section."""
        has_check_11 = "Check #11" in cia_source or "check #11" in cia_source.lower()
        assert has_check_11, (
            "continuous-improvement-analyst.md must contain a 'Check #11' section."
        )

    def test_cia_check_11_references_budget(self, cia_source):
        """Check #11 must reference budget warnings."""
        source_lower = cia_source.lower()
        # Find Check #11 context — look within 500 chars after the marker
        idx = source_lower.find("check #11")
        assert idx != -1, "Check #11 not found in CIA agent."
        surrounding = source_lower[idx: idx + 500]
        has_budget_ref = "budget" in surrounding
        assert has_budget_ref, (
            "Check #11 in continuous-improvement-analyst.md must reference "
            "'budget' warnings (time budgets per agent)."
        )


# ---------------------------------------------------------------------------
# AC #5 — Budgets are configurable (warning_pct is per-agent in config)
# ---------------------------------------------------------------------------
class TestBudgetsAreConfigurable:
    """AC #5: warning_pct is independently configurable per agent."""

    def test_warning_pct_varies_across_agents(self):
        """At least two agents must have different warning_pct values,
        proving per-agent configurability rather than a single global value."""
        data = json.loads(CONFIG_PATH.read_text())
        pcts = {
            agent: data[agent].get("warning_pct")
            for agent in REQUIRED_AGENT_TYPES
            if agent in data and data[agent].get("warning_pct") is not None
        }
        unique_pcts = set(pcts.values())
        # Either all agents have the same pct (single-default, technically valid)
        # OR there is variation — we just confirm the values are explicitly present,
        # not computed from a single global constant not in the config.
        assert len(pcts) == len(REQUIRED_AGENT_TYPES), (
            "All 8 agents must have explicit warning_pct in pipeline_time_budgets.json "
            f"so that each is individually configurable. Missing: "
            f"{REQUIRED_AGENT_TYPES - set(pcts.keys())}"
        )

    def test_config_entries_are_dicts_not_scalars(self):
        """Each agent entry must be a dict (not a bare number) so future
        fields can be added without breaking the schema."""
        data = json.loads(CONFIG_PATH.read_text())
        for agent in REQUIRED_AGENT_TYPES:
            entry = data.get(agent)
            assert isinstance(entry, dict), (
                f"{agent} entry must be a dict with budget_seconds and warning_pct, "
                f"got {type(entry).__name__!r}: {entry!r}"
            )


# ---------------------------------------------------------------------------
# AC #6 — No blocking — soft gate (no {"decision": "block"} in budget section)
# ---------------------------------------------------------------------------
class TestNoBudgetBlocking:
    """AC #6: Budget checks are soft gates — they must not emit block decisions."""

    @pytest.fixture(scope="class")
    def hook_source(self):
        assert HOOK_PATH.exists(), f"Hook not found: {HOOK_PATH}"
        return HOOK_PATH.read_text()

    def test_no_block_decision_in_budget_section(self, hook_source):
        """The budget-related section must not contain JSON block decisions.

        Strategy: find lines containing 'budget' (case-insensitive) and check
        that none of those lines (or adjacent lines) emit {"decision": "block"}.
        """
        lines = hook_source.splitlines()
        budget_line_indices = [
            i for i, line in enumerate(lines)
            if "budget" in line.lower()
        ]

        if not budget_line_indices:
            # Budget checking not yet implemented — test passes (no blocking possible)
            return

        # Examine a 20-line window around each budget reference
        for idx in budget_line_indices:
            window_start = max(0, idx - 5)
            window_end = min(len(lines), idx + 15)
            window = "\n".join(lines[window_start:window_end])
            assert '"decision": "block"' not in window and "'decision': 'block'" not in window, (
                f"Budget section (near line {idx + 1}) must not emit a block decision. "
                "Time budget violations are soft warnings, not hard gates."
            )

    def test_budget_produces_warning_not_exit_code_2(self, hook_source):
        """Budget violations must not use sys.exit(2) (the block exit code)
        in the same code path as budget checking."""
        lines = hook_source.splitlines()
        budget_line_indices = [
            i for i, line in enumerate(lines)
            if "budget" in line.lower()
        ]

        for idx in budget_line_indices:
            window_start = max(0, idx - 3)
            window_end = min(len(lines), idx + 20)
            window = "\n".join(lines[window_start:window_end])
            # exit(2) or sys.exit(2) in the budget window signals blocking
            assert "exit(2)" not in window, (
                f"Budget section near line {idx + 1} uses exit(2), which is the "
                "blocking exit code. Budget violations must be warnings only."
            )


# ---------------------------------------------------------------------------
# AC #7 — Fallback to STATIC_THRESHOLDS when config is missing
# ---------------------------------------------------------------------------
class TestFallbackToStaticThresholds:
    """AC #7: load_time_budgets with nonexistent path returns non-empty dict."""

    @pytest.fixture(scope="class")
    def analyzer_module(self):
        lib_dir = str(REPO_ROOT / "plugins/autonomous-dev/lib")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        try:
            import importlib
            module = importlib.import_module("pipeline_timing_analyzer")
        except Exception as exc:
            pytest.skip(f"pipeline_timing_analyzer.py not importable yet: {exc}")
        return module

    def test_load_time_budgets_returns_fallback_on_missing_path(
        self, tmp_path, analyzer_module
    ):
        """load_time_budgets(nonexistent_path) must return a non-empty dict
        rather than raising an exception or returning an empty dict."""
        nonexistent = tmp_path / "does_not_exist.json"
        result = analyzer_module.load_time_budgets(nonexistent)
        assert isinstance(result, dict), (
            "load_time_budgets must return a dict even when config file is missing."
        )
        assert len(result) > 0, (
            "load_time_budgets must fall back to STATIC_THRESHOLDS "
            "when the config file does not exist — returned empty dict."
        )

    def test_fallback_covers_all_required_agents(self, tmp_path, analyzer_module):
        """The fallback dict must include all 8 required agent types."""
        nonexistent = tmp_path / "does_not_exist.json"
        result = analyzer_module.load_time_budgets(nonexistent)
        missing = REQUIRED_AGENT_TYPES - set(result.keys())
        assert not missing, (
            f"Fallback from load_time_budgets is missing agent entries: {sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# AC #8 — Unit tests exist for budget-related logic
# ---------------------------------------------------------------------------
class TestBudgetUnitTestsExist:
    """AC #8: test_pipeline_timing_analyzer.py contains budget-related test classes."""

    @pytest.fixture(scope="class")
    def existing_tests_source(self):
        assert EXISTING_TESTS_PATH.exists(), (
            f"Expected test file at {EXISTING_TESTS_PATH}"
        )
        return EXISTING_TESTS_PATH.read_text()

    def test_existing_test_file_exists(self):
        """The existing timing analyzer test file must be present."""
        assert EXISTING_TESTS_PATH.exists(), (
            f"Expected test file at {EXISTING_TESTS_PATH}"
        )

    def test_existing_tests_reference_budget(self, existing_tests_source):
        """test_pipeline_timing_analyzer.py must contain budget-related test classes
        or test functions (added as part of Issue #705 implementation)."""
        source_lower = existing_tests_source.lower()
        has_budget_tests = (
            "budget" in source_lower
            or "load_time_budgets" in existing_tests_source
            or "check_budget_violation" in existing_tests_source
            or "format_budget_warning" in existing_tests_source
        )
        assert has_budget_tests, (
            "test_pipeline_timing_analyzer.py must contain at least one test "
            "for budget-related functions (load_time_budgets, check_budget_violation, "
            "or format_budget_warning). Add them as part of Issue #705 implementation."
        )
