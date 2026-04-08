#!/usr/bin/env python3
"""
Acceptance Tests for Issue #714: Pipeline Efficiency Analyzer

These are STATIC FILE INSPECTION tests. They verify code structure, function
exports, config patterns, and algorithm presence without running the full
production pipeline. Tests define the contract that implementation must satisfy.

Acceptance Criteria:
  AC1: save_timing_entry() includes token data (total_tokens, tool_uses fields in JSONL)
  AC2: pipeline_efficiency_analyzer.py exists with analyze_efficiency() function
  AC3: analyze_efficiency() returns findings only when >= 5 observations per agent
  AC4: IQR-based outlier detection is used (compute_iqr_outliers function exists)
  AC5: Model tier recommendations require quality stability (min 10 runs check)
  AC6: CIA Check 14 defined in continuous-improvement-analyst.md
  AC7: All functions have unit tests in test_pipeline_efficiency_analyzer.py
  AC8: Circuit breaker: max 5 findings per report (constant or logic present)
"""

import ast
import json
import sys
import tempfile
from pathlib import Path

import pytest

# Portable project root detection using parents[3] from this file's location:
# tests/unit/lib/test_acceptance_efficiency_analyzer.py -> parents[3] = repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

# Key paths derived from REPO_ROOT
LIB_PATH = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
EFFICIENCY_ANALYZER = LIB_PATH / "pipeline_efficiency_analyzer.py"
TIMING_ANALYZER = LIB_PATH / "pipeline_timing_analyzer.py"
CIA_AGENT = REPO_ROOT / "plugins" / "autonomous-dev" / "agents" / "continuous-improvement-analyst.md"
EFFICIENCY_UNIT_TESTS = REPO_ROOT / "tests" / "unit" / "lib" / "test_pipeline_efficiency_analyzer.py"

sys.path.insert(0, str(LIB_PATH))


# ---------------------------------------------------------------------------
# AC1: save_timing_entry() includes token data fields in JSONL output
# ---------------------------------------------------------------------------

class TestSaveTimingEntryTokenData:
    """AC1: save_timing_entry() JSONL output must include total_tokens and tool_uses."""

    def test_timing_analyzer_includes_total_tokens_field(self):
        """AgentTiming dataclass must have a total_tokens field."""
        source = TIMING_ANALYZER.read_text()
        tree = ast.parse(source)

        timing_class = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "AgentTiming":
                timing_class = node
                break

        assert timing_class is not None, "AgentTiming dataclass not found in pipeline_timing_analyzer.py"

        # Collect field names from the dataclass body
        field_names = set()
        for item in ast.walk(timing_class):
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                field_names.add(item.target.id)

        assert "total_tokens" in field_names, (
            f"AgentTiming is missing 'total_tokens' field. Found fields: {field_names}"
        )

    def test_timing_analyzer_includes_tool_uses_field(self):
        """AgentTiming dataclass must have a tool_uses field."""
        source = TIMING_ANALYZER.read_text()
        tree = ast.parse(source)

        timing_class = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "AgentTiming":
                timing_class = node
                break

        assert timing_class is not None, "AgentTiming dataclass not found in pipeline_timing_analyzer.py"

        field_names = set()
        for item in ast.walk(timing_class):
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                field_names.add(item.target.id)

        assert "tool_uses" in field_names, (
            f"AgentTiming is missing 'tool_uses' field. Found fields: {field_names}"
        )

    def test_save_timing_entry_writes_total_tokens_to_jsonl(self, tmp_path):
        """save_timing_entry() must persist total_tokens in each JSONL line."""
        from pipeline_timing_analyzer import AgentTiming, save_timing_entry

        timing = AgentTiming(
            agent_type="implementer",
            wall_clock_seconds=120.0,
            result_word_count=800,
            invocation_ts="2026-04-01T10:00:00+00:00",
            completion_ts="2026-04-01T10:02:00+00:00",
            total_tokens=15000,
            tool_uses=7,
        )

        history_path = tmp_path / "timing_history.jsonl"
        save_timing_entry([timing], history_path)

        assert history_path.exists(), "save_timing_entry() did not create the JSONL file"

        lines = [ln for ln in history_path.read_text().strip().splitlines() if ln.strip()]
        assert len(lines) >= 1, "JSONL file is empty after save_timing_entry()"

        entry = json.loads(lines[-1])
        assert "total_tokens" in entry, (
            f"JSONL entry missing 'total_tokens'. Keys present: {list(entry.keys())}"
        )
        assert entry["total_tokens"] == 15000, (
            f"total_tokens value mismatch: expected 15000, got {entry['total_tokens']}"
        )

    def test_save_timing_entry_writes_tool_uses_to_jsonl(self, tmp_path):
        """save_timing_entry() must persist tool_uses in each JSONL line."""
        from pipeline_timing_analyzer import AgentTiming, save_timing_entry

        timing = AgentTiming(
            agent_type="researcher",
            wall_clock_seconds=90.0,
            result_word_count=600,
            invocation_ts="2026-04-01T10:00:00+00:00",
            completion_ts="2026-04-01T10:01:30+00:00",
            total_tokens=9000,
            tool_uses=12,
        )

        history_path = tmp_path / "timing_history.jsonl"
        save_timing_entry([timing], history_path)

        lines = [ln for ln in history_path.read_text().strip().splitlines() if ln.strip()]
        entry = json.loads(lines[-1])
        assert "tool_uses" in entry, (
            f"JSONL entry missing 'tool_uses'. Keys present: {list(entry.keys())}"
        )
        assert entry["tool_uses"] == 12, (
            f"tool_uses value mismatch: expected 12, got {entry['tool_uses']}"
        )

    def test_save_timing_entry_zero_tokens_does_not_omit_field(self, tmp_path):
        """save_timing_entry() must write token fields even when values are 0."""
        from pipeline_timing_analyzer import AgentTiming, save_timing_entry

        timing = AgentTiming(
            agent_type="doc-master",
            wall_clock_seconds=45.0,
            result_word_count=200,
            invocation_ts="2026-04-01T10:00:00+00:00",
            completion_ts="2026-04-01T10:00:45+00:00",
            total_tokens=0,
            tool_uses=0,
        )

        history_path = tmp_path / "timing_history.jsonl"
        save_timing_entry([timing], history_path)

        lines = [ln for ln in history_path.read_text().strip().splitlines() if ln.strip()]
        entry = json.loads(lines[-1])
        # Both fields must be present (even as 0) so load_timing_history can read them
        assert "total_tokens" in entry, "JSONL entry must include total_tokens even when 0"
        assert "tool_uses" in entry, "JSONL entry must include tool_uses even when 0"


# ---------------------------------------------------------------------------
# AC2: pipeline_efficiency_analyzer.py exists with analyze_efficiency()
# ---------------------------------------------------------------------------

class TestEfficiencyAnalyzerFileExists:
    """AC2: pipeline_efficiency_analyzer.py must exist with analyze_efficiency()."""

    def test_efficiency_analyzer_file_exists(self):
        """pipeline_efficiency_analyzer.py must be present in the lib directory."""
        assert EFFICIENCY_ANALYZER.exists(), (
            f"pipeline_efficiency_analyzer.py not found at: {EFFICIENCY_ANALYZER}\n"
            "This file must be created as part of Issue #714."
        )

    def test_analyze_efficiency_function_exists(self):
        """analyze_efficiency() must be defined in pipeline_efficiency_analyzer.py."""
        assert EFFICIENCY_ANALYZER.exists(), "pipeline_efficiency_analyzer.py not found"

        source = EFFICIENCY_ANALYZER.read_text()
        tree = ast.parse(source)

        func_names = {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        assert "analyze_efficiency" in func_names, (
            f"analyze_efficiency() not found in pipeline_efficiency_analyzer.py. "
            f"Functions found: {sorted(func_names)}"
        )

    def test_analyze_efficiency_is_importable(self):
        """analyze_efficiency must be importable from pipeline_efficiency_analyzer."""
        pytest.importorskip("pipeline_efficiency_analyzer")
        from pipeline_efficiency_analyzer import analyze_efficiency  # noqa: F401


# ---------------------------------------------------------------------------
# AC3: analyze_efficiency() returns findings only when >= 5 observations
# ---------------------------------------------------------------------------

class TestMinObservationsGate:
    """AC3: analyze_efficiency() must require >= 5 observations per agent."""

    def test_analyze_efficiency_returns_empty_below_threshold(self):
        """With < 5 observations, analyze_efficiency() must return no findings."""
        pytest.importorskip("pipeline_efficiency_analyzer")
        from pipeline_efficiency_analyzer import analyze_efficiency

        # 4 observations — below the 5-observation minimum
        observations = [
            {"agent_type": "researcher", "wall_clock_seconds": 100.0, "total_tokens": 5000}
            for _ in range(4)
        ]

        findings = analyze_efficiency(observations)
        assert isinstance(findings, list), "analyze_efficiency() must return a list"
        assert len(findings) == 0, (
            f"analyze_efficiency() returned {len(findings)} findings for only 4 observations. "
            "Must return empty list when < 5 observations exist per agent."
        )

    def test_analyze_efficiency_can_return_findings_at_threshold(self):
        """With exactly 5 observations, analyze_efficiency() may return findings."""
        pytest.importorskip("pipeline_efficiency_analyzer")
        from pipeline_efficiency_analyzer import analyze_efficiency

        # 5 observations meeting the minimum — result may or may not have findings,
        # but must not raise and must return a list
        observations = [
            {"agent_type": "implementer", "wall_clock_seconds": 600.0, "total_tokens": 200000}
            for _ in range(5)
        ]

        findings = analyze_efficiency(observations)
        assert isinstance(findings, list), (
            "analyze_efficiency() must return a list with >= 5 observations"
        )

    def test_min_observations_constant_is_five_or_less(self):
        """The minimum observations constant must be defined and <= 5."""
        pytest.importorskip("pipeline_efficiency_analyzer")
        import pipeline_efficiency_analyzer as module

        # Look for a constant — either MIN_OBSERVATIONS, MIN_EFFICIENCY_OBSERVATIONS, or similar
        min_constant = None
        for attr in dir(module):
            if "min" in attr.lower() and "obs" in attr.lower():
                val = getattr(module, attr)
                if isinstance(val, int):
                    min_constant = val
                    break

        assert min_constant is not None, (
            "No MIN_OBSERVATIONS-style constant found in pipeline_efficiency_analyzer. "
            "Expected a constant like MIN_OBSERVATIONS = 5."
        )
        assert min_constant <= 5, (
            f"Minimum observations constant is {min_constant}, expected <= 5 per AC3."
        )


# ---------------------------------------------------------------------------
# AC4: IQR-based outlier detection (compute_iqr_outliers function exists)
# ---------------------------------------------------------------------------

class TestIQROutlierDetection:
    """AC4: compute_iqr_outliers() must exist and implement IQR logic."""

    def test_compute_iqr_outliers_function_exists(self):
        """compute_iqr_outliers() must be defined in pipeline_efficiency_analyzer.py."""
        assert EFFICIENCY_ANALYZER.exists(), "pipeline_efficiency_analyzer.py not found"

        source = EFFICIENCY_ANALYZER.read_text()
        tree = ast.parse(source)

        func_names = {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        assert "compute_iqr_outliers" in func_names, (
            f"compute_iqr_outliers() not found in pipeline_efficiency_analyzer.py. "
            f"Functions present: {sorted(func_names)}"
        )

    def test_compute_iqr_outliers_is_importable(self):
        """compute_iqr_outliers must be importable."""
        pytest.importorskip("pipeline_efficiency_analyzer")
        from pipeline_efficiency_analyzer import compute_iqr_outliers  # noqa: F401

    def test_compute_iqr_outliers_uses_quartile_logic(self):
        """compute_iqr_outliers() source must contain IQR / quartile computation."""
        assert EFFICIENCY_ANALYZER.exists(), "pipeline_efficiency_analyzer.py not found"

        source = EFFICIENCY_ANALYZER.read_text()

        # IQR = Q3 - Q1. The source must reference quartile computation.
        # Accept any of these canonical patterns.
        iqr_indicators = [
            "q1", "q3", "quartile", "iqr", "percentile", "25", "75",
        ]
        source_lower = source.lower()
        matches = [indicator for indicator in iqr_indicators if indicator in source_lower]

        assert len(matches) >= 2, (
            "compute_iqr_outliers() does not appear to implement IQR logic. "
            f"Expected quartile-related terms (q1, q3, iqr, percentile). "
            f"Found only: {matches}"
        )

    def test_compute_iqr_outliers_detects_high_outliers(self):
        """compute_iqr_outliers() must flag values far above the IQR upper fence."""
        pytest.importorskip("pipeline_efficiency_analyzer")
        from pipeline_efficiency_analyzer import compute_iqr_outliers

        # 8 normal values around 100s, one extreme outlier at 900s
        values = [95.0, 100.0, 102.0, 98.0, 101.0, 99.0, 103.0, 97.0, 900.0]
        outliers = compute_iqr_outliers(values)

        assert isinstance(outliers, (list, set, tuple)), (
            "compute_iqr_outliers() must return a collection of outlier values or indices"
        )
        # The 900.0 value should be flagged
        outlier_values = list(outliers)
        assert any(v == 900.0 or (isinstance(v, (int, float)) and v > 500) for v in outlier_values), (
            f"compute_iqr_outliers() did not flag the extreme outlier (900.0). "
            f"Returned: {outlier_values}"
        )

    def test_compute_iqr_outliers_returns_empty_for_uniform_data(self):
        """compute_iqr_outliers() must return no outliers for uniform data."""
        pytest.importorskip("pipeline_efficiency_analyzer")
        from pipeline_efficiency_analyzer import compute_iqr_outliers

        # All values identical — no IQR spread, no outliers
        values = [100.0] * 10
        outliers = compute_iqr_outliers(values)

        assert len(outliers) == 0, (
            f"compute_iqr_outliers() returned outliers for uniform data: {outliers}"
        )


# ---------------------------------------------------------------------------
# AC5: Model tier recommendations require quality stability (min 10 runs)
# ---------------------------------------------------------------------------

class TestModelTierRecommendationGate:
    """AC5: Model tier recommendations must only fire after >= 10 runs."""

    def test_model_tier_recommendation_min_runs_constant_defined(self):
        """A minimum run constant for model tier recommendations must exist."""
        pytest.importorskip("pipeline_efficiency_analyzer")
        import pipeline_efficiency_analyzer as module

        # Look for a constant with "model", "tier", or "run" in the name
        tier_constant = None
        for attr in dir(module):
            attr_lower = attr.lower()
            if any(kw in attr_lower for kw in ("model_tier", "tier_min", "min_run", "stability")):
                val = getattr(module, attr)
                if isinstance(val, int):
                    tier_constant = val
                    break

        assert tier_constant is not None, (
            "No model tier / stability minimum constant found in pipeline_efficiency_analyzer. "
            "Expected a constant like MIN_RUNS_FOR_TIER_RECOMMENDATION = 10."
        )
        assert tier_constant >= 10, (
            f"Model tier recommendation minimum runs is {tier_constant}. "
            "AC5 requires at least 10 runs before recommending a model tier change."
        )

    def test_analyze_efficiency_no_tier_recommendation_below_10_runs(self):
        """analyze_efficiency() must not recommend model tier changes with < 10 runs."""
        pytest.importorskip("pipeline_efficiency_analyzer")
        from pipeline_efficiency_analyzer import analyze_efficiency

        # 9 runs with high token usage (potential tier recommendation candidate)
        observations = [
            {
                "agent_type": "researcher-local",
                "wall_clock_seconds": 60.0,
                "total_tokens": 150000,
                "tool_uses": 5,
            }
            for _ in range(9)
        ]

        findings = analyze_efficiency(observations)

        # No findings should recommend model tier changes with only 9 runs
        tier_findings = [
            f for f in findings
            if isinstance(f, dict) and "tier" in str(f).lower()
        ]

        assert len(tier_findings) == 0, (
            f"analyze_efficiency() issued {len(tier_findings)} model tier recommendation(s) "
            f"with only 9 runs. Must require >= 10 runs per AC5. Findings: {tier_findings}"
        )

    def test_source_contains_min_runs_check_logic(self):
        """pipeline_efficiency_analyzer.py source must contain a 10-run check."""
        assert EFFICIENCY_ANALYZER.exists(), "pipeline_efficiency_analyzer.py not found"

        source = EFFICIENCY_ANALYZER.read_text()

        # The number 10 must appear near context suggesting a minimum threshold
        # Accept either the literal 10 in a constant assignment or >= 10 in comparison
        has_ten = "10" in source
        has_threshold_context = any(kw in source.lower() for kw in [
            "min_run", "stability", "tier", "model_tier", "recommendation"
        ])

        assert has_ten and has_threshold_context, (
            "pipeline_efficiency_analyzer.py does not appear to contain a 10-run "
            "minimum check for model tier recommendations. "
            "Expected a constant or conditional with value 10 near 'tier'/'stability' context."
        )


# ---------------------------------------------------------------------------
# AC6: CIA Check 14 defined in continuous-improvement-analyst.md
# ---------------------------------------------------------------------------

class TestCIACheck14:
    """AC6: continuous-improvement-analyst.md must define Check #14."""

    def test_cia_agent_file_exists(self):
        """continuous-improvement-analyst.md must exist."""
        assert CIA_AGENT.exists(), (
            f"continuous-improvement-analyst.md not found at: {CIA_AGENT}"
        )

    def test_cia_defines_check_14(self):
        """The CIA agent must have a Check #14 section."""
        content = CIA_AGENT.read_text()

        has_check_14 = (
            "14." in content or
            "Check #14" in content or
            "Check 14" in content or
            "**14.**" in content or
            "### 14" in content
        )

        assert has_check_14, (
            "continuous-improvement-analyst.md does not define Check #14. "
            "AC6 requires adding CIA Check 14 for pipeline efficiency analysis. "
            "Currently defined checks end before 14."
        )

    def test_cia_check_14_references_efficiency_analyzer(self):
        """CIA Check 14 must reference pipeline_efficiency_analyzer."""
        content = CIA_AGENT.read_text()

        # Find the section containing check 14
        check_14_index = -1
        for marker in ["14.", "Check #14", "Check 14"]:
            idx = content.find(marker)
            if idx != -1:
                check_14_index = idx
                break

        assert check_14_index != -1, (
            "Check #14 marker not found in continuous-improvement-analyst.md"
        )

        # The content after Check 14 marker (within next 1000 chars) must reference
        # the efficiency analyzer
        context_window = content[check_14_index:check_14_index + 1000]
        assert "pipeline_efficiency_analyzer" in context_window or "efficiency" in context_window.lower(), (
            "CIA Check #14 does not reference pipeline_efficiency_analyzer or efficiency analysis. "
            f"Content near Check 14: {context_window[:300]}"
        )

    def test_cia_check_14_references_analyze_efficiency(self):
        """CIA Check 14 must instruct calling analyze_efficiency()."""
        content = CIA_AGENT.read_text()

        check_14_index = -1
        for marker in ["14.", "Check #14", "Check 14"]:
            idx = content.find(marker)
            if idx != -1:
                check_14_index = idx
                break

        if check_14_index == -1:
            pytest.skip("Check #14 not yet defined — covered by test_cia_defines_check_14")

        context_window = content[check_14_index:check_14_index + 1000]
        assert "analyze_efficiency" in context_window, (
            "CIA Check #14 does not instruct calling analyze_efficiency(). "
            f"Content near Check 14: {context_window[:300]}"
        )


# ---------------------------------------------------------------------------
# AC7: All functions have unit tests in test_pipeline_efficiency_analyzer.py
# ---------------------------------------------------------------------------

class TestEfficiencyAnalyzerUnitTestFile:
    """AC7: test_pipeline_efficiency_analyzer.py must exist and cover core functions."""

    def test_unit_test_file_exists(self):
        """tests/unit/lib/test_pipeline_efficiency_analyzer.py must exist."""
        assert EFFICIENCY_UNIT_TESTS.exists(), (
            f"test_pipeline_efficiency_analyzer.py not found at: {EFFICIENCY_UNIT_TESTS}\n"
            "AC7 requires a dedicated unit test file for the efficiency analyzer."
        )

    def test_unit_test_file_covers_analyze_efficiency(self):
        """test_pipeline_efficiency_analyzer.py must test analyze_efficiency()."""
        assert EFFICIENCY_UNIT_TESTS.exists(), "Unit test file not found"

        content = EFFICIENCY_UNIT_TESTS.read_text()
        assert "analyze_efficiency" in content, (
            "test_pipeline_efficiency_analyzer.py does not test analyze_efficiency(). "
            "AC7 requires unit tests for all public functions."
        )

    def test_unit_test_file_covers_compute_iqr_outliers(self):
        """test_pipeline_efficiency_analyzer.py must test compute_iqr_outliers()."""
        assert EFFICIENCY_UNIT_TESTS.exists(), "Unit test file not found"

        content = EFFICIENCY_UNIT_TESTS.read_text()
        assert "compute_iqr_outliers" in content, (
            "test_pipeline_efficiency_analyzer.py does not test compute_iqr_outliers(). "
            "AC7 requires unit tests for all public functions."
        )

    def test_unit_test_file_has_minimum_test_functions(self):
        """test_pipeline_efficiency_analyzer.py must contain at least 5 test functions."""
        assert EFFICIENCY_UNIT_TESTS.exists(), "Unit test file not found"

        source = EFFICIENCY_UNIT_TESTS.read_text()
        tree = ast.parse(source)

        test_funcs = [
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        ]

        assert len(test_funcs) >= 5, (
            f"test_pipeline_efficiency_analyzer.py has only {len(test_funcs)} test function(s). "
            "AC7 requires unit tests for ALL functions — expected at least 5."
        )

    def test_unit_test_file_imports_efficiency_module(self):
        """test_pipeline_efficiency_analyzer.py must import from pipeline_efficiency_analyzer."""
        assert EFFICIENCY_UNIT_TESTS.exists(), "Unit test file not found"

        content = EFFICIENCY_UNIT_TESTS.read_text()
        assert "pipeline_efficiency_analyzer" in content, (
            "test_pipeline_efficiency_analyzer.py does not import pipeline_efficiency_analyzer. "
            "The test file must import and exercise the module it tests."
        )


# ---------------------------------------------------------------------------
# AC8: Circuit breaker — max 5 findings per report
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    """AC8: Circuit breaker must cap findings at max 5 per report."""

    def test_max_findings_constant_defined(self):
        """A MAX_FINDINGS constant (or equivalent) must be defined in the module."""
        pytest.importorskip("pipeline_efficiency_analyzer")
        import pipeline_efficiency_analyzer as module

        # Accept any constant name containing MAX and FINDING
        max_finding_constant = None
        for attr in dir(module):
            attr_upper = attr.upper()
            if "MAX" in attr_upper and ("FINDING" in attr_upper or "REPORT" in attr_upper or "CIRCUIT" in attr_upper):
                val = getattr(module, attr)
                if isinstance(val, int):
                    max_finding_constant = val
                    break

        assert max_finding_constant is not None, (
            "No MAX_FINDINGS-style constant found in pipeline_efficiency_analyzer. "
            "AC8 requires a circuit breaker constant (e.g., MAX_FINDINGS_PER_REPORT = 5)."
        )
        assert max_finding_constant <= 5, (
            f"Circuit breaker constant is {max_finding_constant}. "
            "AC8 requires max 5 findings per report — constant must be <= 5."
        )

    def test_analyze_efficiency_caps_findings_at_five(self):
        """analyze_efficiency() must never return more than 5 findings."""
        pytest.importorskip("pipeline_efficiency_analyzer")
        from pipeline_efficiency_analyzer import analyze_efficiency

        # Generate many agents with many observations to try to trigger many findings
        observations = []
        agent_types = ["researcher", "planner", "implementer", "reviewer", "doc-master",
                       "researcher-local", "security-auditor", "test-master"]
        for agent in agent_types:
            for _ in range(10):
                observations.append({
                    "agent_type": agent,
                    "wall_clock_seconds": 9999.0,   # extreme duration
                    "total_tokens": 999999,           # extreme token use
                    "tool_uses": 100,
                })

        findings = analyze_efficiency(observations)

        assert isinstance(findings, list), "analyze_efficiency() must return a list"
        assert len(findings) <= 5, (
            f"analyze_efficiency() returned {len(findings)} findings, violating the "
            "circuit breaker limit of 5 per report (AC8)."
        )

    def test_source_contains_circuit_breaker_logic(self):
        """pipeline_efficiency_analyzer.py source must contain circuit breaker logic."""
        assert EFFICIENCY_ANALYZER.exists(), "pipeline_efficiency_analyzer.py not found"

        source = EFFICIENCY_ANALYZER.read_text()

        # The source must contain the number 5 in a context that looks like a cap
        # Accept constant assignment or slice/comparison patterns
        has_five = "5" in source
        has_circuit_context = any(kw in source.lower() for kw in [
            "max_finding", "circuit", "findings[:5]", "findings[:max", "cap", "limit"
        ])

        assert has_five and has_circuit_context, (
            "pipeline_efficiency_analyzer.py does not appear to contain circuit breaker "
            "logic capping findings at 5. Expected a constant or slice like findings[:5] "
            "or findings[:MAX_FINDINGS_PER_REPORT]."
        )


# ---------------------------------------------------------------------------
# Structural / file-level checks (supporting all ACs)
# ---------------------------------------------------------------------------

class TestStructuralRequirements:
    """Structural checks validating overall file layout and imports."""

    def test_efficiency_analyzer_has_module_docstring(self):
        """pipeline_efficiency_analyzer.py must have a module-level docstring."""
        assert EFFICIENCY_ANALYZER.exists(), "pipeline_efficiency_analyzer.py not found"

        source = EFFICIENCY_ANALYZER.read_text()
        tree = ast.parse(source)

        # Module docstring is the first statement if it's an Expr with a Constant
        has_docstring = (
            tree.body
            and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
            and isinstance(tree.body[0].value.value, str)
        )

        assert has_docstring, (
            "pipeline_efficiency_analyzer.py lacks a module-level docstring. "
            "All library files must have docstrings per python-standards."
        )

    def test_efficiency_analyzer_imports_timing_analyzer(self):
        """pipeline_efficiency_analyzer.py should import from pipeline_timing_analyzer."""
        assert EFFICIENCY_ANALYZER.exists(), "pipeline_efficiency_analyzer.py not found"

        source = EFFICIENCY_ANALYZER.read_text()

        assert "pipeline_timing_analyzer" in source, (
            "pipeline_efficiency_analyzer.py does not import from pipeline_timing_analyzer. "
            "The efficiency analyzer should build on the timing analyzer's data structures."
        )

    def test_analyze_efficiency_has_docstring(self):
        """analyze_efficiency() must have a docstring."""
        assert EFFICIENCY_ANALYZER.exists(), "pipeline_efficiency_analyzer.py not found"

        source = EFFICIENCY_ANALYZER.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "analyze_efficiency":
                has_docstring = (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                )
                assert has_docstring, (
                    "analyze_efficiency() is missing a docstring. "
                    "All public functions must have docstrings per python-standards."
                )
                return

        pytest.skip("analyze_efficiency() not found — covered by AC2 tests")

    def test_timing_analyzer_file_exists(self):
        """pipeline_timing_analyzer.py must exist (dependency of efficiency analyzer)."""
        assert TIMING_ANALYZER.exists(), (
            f"pipeline_timing_analyzer.py not found at: {TIMING_ANALYZER}. "
            "This is a dependency for pipeline_efficiency_analyzer.py."
        )
