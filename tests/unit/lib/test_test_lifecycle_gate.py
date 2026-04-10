"""Unit tests for check_prunable_threshold() and PRUNABLE_THRESHOLD gate.

Tests the CI gate tooling added in Issue #736.
"""

import sys
from pathlib import Path

import pytest

# Path setup: tests/unit/lib/ -> parents[3] = repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
LIB_PATH = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_PATH))

from test_lifecycle_manager import (
    PRUNABLE_THRESHOLD,
    TestHealthReport,
    TestHealthSummary,
    TestLifecycleManager,
    check_prunable_threshold,
)


def _make_report(*, prunable_count: int = 0) -> TestHealthReport:
    """Helper to create a TestHealthReport with a given prunable count."""
    report = TestHealthReport()
    report.summary = TestHealthSummary(prunable_count=prunable_count)
    return report


class TestCheckPrunableThreshold:
    """Tests for check_prunable_threshold()."""

    def test_threshold_passes_when_below_limit(self) -> None:
        """Prunable count below threshold should pass."""
        report = _make_report(prunable_count=50)
        passed, msg = check_prunable_threshold(report)
        assert passed is True
        assert "within threshold" in msg

    def test_threshold_fails_when_above_limit(self) -> None:
        """Prunable count above threshold should fail."""
        report = _make_report(prunable_count=150)
        passed, msg = check_prunable_threshold(report)
        assert passed is False
        assert "exceeds threshold" in msg
        assert "/sweep --tests --prune" in msg

    def test_threshold_custom_value(self) -> None:
        """Custom threshold value should be respected."""
        report = _make_report(prunable_count=20)
        # Should pass with threshold 50
        passed, msg = check_prunable_threshold(report, threshold=50)
        assert passed is True

        # Should fail with threshold 10
        passed, msg = check_prunable_threshold(report, threshold=10)
        assert passed is False

    def test_threshold_zero_prunable_passes(self) -> None:
        """Zero prunable findings should always pass."""
        report = _make_report(prunable_count=0)
        passed, msg = check_prunable_threshold(report)
        assert passed is True
        assert "0" in msg

    def test_threshold_default_is_100(self) -> None:
        """Default PRUNABLE_THRESHOLD constant should be 100."""
        assert PRUNABLE_THRESHOLD == 100

    def test_threshold_at_exact_limit_passes(self) -> None:
        """Prunable count exactly at threshold should pass (<=, not <)."""
        report = _make_report(prunable_count=100)
        passed, msg = check_prunable_threshold(report, threshold=100)
        assert passed is True


class TestDashboardGateStatus:
    """Tests for gate status in format_dashboard output."""

    def test_dashboard_includes_gate_status_pass(self) -> None:
        """Dashboard should include Gate Status: PASS when below threshold."""
        report = _make_report(prunable_count=50)
        manager = TestLifecycleManager(REPO_ROOT)
        dashboard = manager.format_dashboard(report)
        assert "Gate Status: PASS" in dashboard

    def test_dashboard_includes_gate_status_fail(self) -> None:
        """Dashboard should include Gate Status: FAIL when above threshold."""
        report = _make_report(prunable_count=200)
        manager = TestLifecycleManager(REPO_ROOT)
        dashboard = manager.format_dashboard(report)
        assert "Gate Status: FAIL" in dashboard
        assert "/sweep --tests --prune" in dashboard
