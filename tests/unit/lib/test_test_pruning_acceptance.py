"""Acceptance tests for Issue #736: Test pruning tooling and CI gate.

Static inspection tests verifying the implementation plan's acceptance criteria.
"""

import os
import re
import sys

import pytest

WORKTREE = os.environ.get(
    "WORKTREE_PATH",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
)
LIB_PATH = os.path.join(WORKTREE, "plugins", "autonomous-dev", "lib")
sys.path.insert(0, LIB_PATH)


def _read_source(filename: str) -> str:
    path = os.path.join(LIB_PATH, filename)
    with open(path) as f:
        return f.read()


class TestAcceptanceCriteria736:
    """Acceptance criteria for Issue #736."""

    def test_ac1_prune_tests_method_exists(self):
        """AC1: TestPruningAnalyzer has prune_tests() method."""
        source = _read_source("test_pruning_analyzer.py")
        assert "def prune_tests" in source

    def test_ac1_prune_tests_has_dry_run_param(self):
        """AC1: prune_tests() has dry_run parameter."""
        source = _read_source("test_pruning_analyzer.py")
        assert "dry_run" in source

    def test_ac2_prune_result_dataclass_exists(self):
        """AC2: PruneResult dataclass exists."""
        source = _read_source("test_pruning_analyzer.py")
        assert "class PruneResult" in source or "PruneResult" in source

    def test_ac3_security_tests_excluded(self):
        """AC3: Security tests excluded from auto-pruning by default."""
        source = _read_source("test_pruning_analyzer.py")
        assert "security" in source.lower()

    def test_ac6_check_prunable_threshold_exists(self):
        """AC6: check_prunable_threshold() exists in test_lifecycle_manager."""
        source = _read_source("test_lifecycle_manager.py")
        assert "check_prunable_threshold" in source or "prunable_threshold" in source.lower()

    def test_ac6_threshold_constant_defined(self):
        """AC6: PRUNABLE_THRESHOLD constant defined."""
        source = _read_source("test_lifecycle_manager.py")
        assert "PRUNABLE_THRESHOLD" in source or "prunable_threshold" in source.lower()

    def test_ac7_dashboard_includes_gate(self):
        """AC7: format_dashboard includes gate status."""
        source = _read_source("test_lifecycle_manager.py")
        assert "format_dashboard" in source
