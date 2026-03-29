#!/usr/bin/env python3
"""Tests for batch_mode_detector — per-issue pipeline mode detection.

Issue: #600
"""

import sys
from pathlib import Path

import pytest

# Add lib to path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"))

from batch_mode_detector import (
    FIX_SIGNALS,
    LIGHT_SIGNALS,
    ModeDetection,
    PipelineMode,
    detect_batch_modes,
    detect_issue_mode,
    format_mode_summary_table,
)


# =============================================================================
# PipelineMode enum
# =============================================================================


class TestPipelineMode:
    def test_values(self):
        assert PipelineMode.FULL.value == "full"
        assert PipelineMode.FIX.value == "fix"
        assert PipelineMode.LIGHT.value == "light"


# =============================================================================
# detect_issue_mode — fix signals
# =============================================================================


class TestDetectFixSignals:
    def test_fix_signal_in_title(self):
        result = detect_issue_mode("Fix failing test in auth module")
        assert result.mode == PipelineMode.FIX
        assert result.source == "title"
        assert len(result.signals) > 0

    def test_fix_signal_in_body(self):
        result = detect_issue_mode("Auth module issue", body="There is a bug in login")
        assert result.mode == PipelineMode.FIX
        assert result.source == "body"

    def test_fix_signal_in_both(self):
        result = detect_issue_mode("Fix broken login", body="This bug causes crashes")
        assert result.mode == PipelineMode.FIX
        assert len(result.signals) >= 2

    def test_regression_signal(self):
        result = detect_issue_mode("Fix regression in parser")
        assert result.mode == PipelineMode.FIX

    def test_crash_signal(self):
        result = detect_issue_mode("App crash on startup")
        assert result.mode == PipelineMode.FIX

    def test_error_signal(self):
        result = detect_issue_mode("TypeError error in handler")
        assert result.mode == PipelineMode.FIX

    def test_flaky_test_signal(self):
        result = detect_issue_mode("Address flaky test in CI")
        assert result.mode == PipelineMode.FIX


# =============================================================================
# detect_issue_mode — light signals
# =============================================================================


class TestDetectLightSignals:
    def test_light_signal_in_title(self):
        result = detect_issue_mode("Update README with setup instructions")
        assert result.mode == PipelineMode.LIGHT
        assert result.source == "title"

    def test_light_signal_in_body(self):
        result = detect_issue_mode("Improve onboarding", body="Need to update docs for new API")
        assert result.mode == PipelineMode.LIGHT
        assert result.source == "body"

    def test_typo_signal(self):
        result = detect_issue_mode("Fix typo in configuration guide")
        assert result.mode == PipelineMode.LIGHT

    def test_changelog_signal(self):
        result = detect_issue_mode("Update changelog for v2.0")
        assert result.mode == PipelineMode.LIGHT

    def test_rename_signal(self):
        result = detect_issue_mode("Rename old config variable")
        assert result.mode == PipelineMode.LIGHT

    def test_config_change_signal(self):
        result = detect_issue_mode("Apply config change for production")
        assert result.mode == PipelineMode.LIGHT

    def test_update_comment_signal(self):
        result = detect_issue_mode("Update comment in main module")
        assert result.mode == PipelineMode.LIGHT


# =============================================================================
# detect_issue_mode — tie-break and default
# =============================================================================


class TestDetectTieBreakAndDefault:
    def test_tie_break_fix_wins(self):
        """When both fix and light signals are present with equal score, fix wins."""
        result = detect_issue_mode("Fix typo in error handler")
        # "typo" is light, "error" is fix — both in title (2 pts each)
        assert result.mode == PipelineMode.FIX

    def test_no_signals_returns_full(self):
        result = detect_issue_mode("Add JWT authentication feature")
        assert result.mode == PipelineMode.FULL
        assert result.confidence == 0.0
        assert result.source == "default"
        assert result.signals == []

    def test_empty_title_returns_full(self):
        result = detect_issue_mode("")
        assert result.mode == PipelineMode.FULL

    def test_empty_title_and_body_returns_full(self):
        result = detect_issue_mode("", body="")
        assert result.mode == PipelineMode.FULL


# =============================================================================
# detect_issue_mode — label overrides
# =============================================================================


class TestDetectLabelOverrides:
    def test_bug_label_overrides_to_fix(self):
        result = detect_issue_mode("Update readme", labels=["bug"])
        assert result.mode == PipelineMode.FIX
        assert result.source == "label"
        assert result.confidence == 1.0

    def test_documentation_label_overrides_to_light(self):
        result = detect_issue_mode("Add feature", labels=["documentation"])
        assert result.mode == PipelineMode.LIGHT
        assert result.source == "label"
        assert result.confidence == 1.0

    def test_bug_label_beats_light_signals(self):
        """Bug label should override even if title has light signals."""
        result = detect_issue_mode("Update README", labels=["bug"])
        assert result.mode == PipelineMode.FIX

    def test_documentation_label_beats_fix_signals(self):
        """Documentation label should override even if title has fix signals."""
        result = detect_issue_mode("Fix broken test", labels=["documentation"])
        assert result.mode == PipelineMode.LIGHT

    def test_bug_label_beats_documentation_label(self):
        """When both bug and documentation labels present, bug (fix) wins."""
        result = detect_issue_mode("Some issue", labels=["documentation", "bug"])
        assert result.mode == PipelineMode.FIX

    def test_label_case_insensitive(self):
        result = detect_issue_mode("Some issue", labels=["Bug"])
        assert result.mode == PipelineMode.FIX

    def test_no_labels_defaults(self):
        result = detect_issue_mode("Some issue", labels=[])
        assert result.mode == PipelineMode.FULL


# =============================================================================
# detect_issue_mode — case insensitivity
# =============================================================================


class TestCaseInsensitivity:
    def test_fix_signal_uppercase(self):
        result = detect_issue_mode("FIX FAILING TEST IN AUTH")
        assert result.mode == PipelineMode.FIX

    def test_light_signal_mixed_case(self):
        result = detect_issue_mode("Update README Section")
        assert result.mode == PipelineMode.LIGHT


# =============================================================================
# detect_batch_modes
# =============================================================================


class TestDetectBatchModes:
    def test_batch_basic(self):
        issues = [
            {"title": "Fix failing test in auth"},
            {"title": "Add JWT authentication"},
            {"title": "Update README setup section"},
        ]
        results = detect_batch_modes(issues)
        assert len(results) == 3
        assert results[0].mode == PipelineMode.FIX
        assert results[1].mode == PipelineMode.FULL
        assert results[2].mode == PipelineMode.LIGHT

    def test_batch_with_labels_as_dicts(self):
        """GitHub API returns labels as list of dicts with 'name' key."""
        issues = [
            {"title": "Some issue", "labels": [{"name": "bug"}]},
        ]
        results = detect_batch_modes(issues)
        assert results[0].mode == PipelineMode.FIX

    def test_batch_with_body(self):
        issues = [
            {"title": "Improve module", "body": "There is a bug in the parser"},
        ]
        results = detect_batch_modes(issues)
        assert results[0].mode == PipelineMode.FIX

    def test_batch_empty_list(self):
        results = detect_batch_modes([])
        assert results == []

    def test_batch_missing_keys(self):
        """Issues with missing keys should default to FULL."""
        issues = [{"title": ""}]
        results = detect_batch_modes(issues)
        assert results[0].mode == PipelineMode.FULL

    def test_batch_none_body(self):
        """Body can be None from GitHub API."""
        issues = [{"title": "Fix bug", "body": None}]
        results = detect_batch_modes(issues)
        assert results[0].mode == PipelineMode.FIX


# =============================================================================
# format_mode_summary_table
# =============================================================================


class TestFormatModeSummaryTable:
    def test_basic_table(self):
        modes = [
            ModeDetection(mode=PipelineMode.FIX, signals=['"failing test" (title)'], source="title"),
            ModeDetection(mode=PipelineMode.FULL, signals=[], source="default"),
            ModeDetection(mode=PipelineMode.LIGHT, signals=['"readme" (title)'], source="title"),
        ]
        table = format_mode_summary_table(
            [101, 102, 103],
            ["Fix failing test in auth", "Add JWT authentication", "Update README setup section"],
            modes,
        )
        assert "#101" in table
        assert "#102" in table
        assert "#103" in table
        assert "--fix" in table
        assert "full" in table
        assert "--light" in table
        assert "(no signals)" in table
        assert "Issue" in table  # header

    def test_empty_input(self):
        result = format_mode_summary_table([], [], [])
        assert result == ""

    def test_long_title_truncation(self):
        long_title = "A" * 50
        modes = [ModeDetection(mode=PipelineMode.FULL)]
        table = format_mode_summary_table([1], [long_title], modes)
        assert "..." in table

    def test_table_has_header(self):
        modes = [ModeDetection(mode=PipelineMode.FULL)]
        table = format_mode_summary_table([1], ["Test"], modes)
        assert "Issue" in table
        assert "Title" in table
        assert "Detected Mode" in table
        assert "Signals" in table
