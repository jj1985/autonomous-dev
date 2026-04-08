#!/usr/bin/env python3
"""
Tests for budget-checking integration in session_activity_logger.py (Issue #705).

Validates that BudgetWarning JSONL entries are logged for slow agents and that
the budget check is non-blocking even when the timing library is unavailable.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Portable project root detection
_current = Path(__file__).resolve()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        REPO_ROOT = _current
        break
    _current = _current.parent
else:
    REPO_ROOT = Path(__file__).resolve().parents[3]

HOOK_PATH = REPO_ROOT / "plugins/autonomous-dev/hooks/session_activity_logger.py"
LIB_DIR = REPO_ROOT / "plugins/autonomous-dev/lib"

# Add lib dir to path so the budget helper can import pipeline_timing_analyzer
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

# Import the budget helper directly
sys.path.insert(0, str(HOOK_PATH.parent))


def _load_hook_module():
    """Load session_activity_logger as a module (not via subprocess)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("session_activity_logger", HOOK_PATH)
    assert spec is not None and spec.loader is not None, f"Cannot load {HOOK_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class TestBudgetWarningLogged:
    """BudgetWarning entries are written for agents that approach or exceed budget."""

    @pytest.fixture
    def hook_module(self):
        return _load_hook_module()

    def test_budget_warning_logged_for_slow_agent(self, tmp_path: Path, hook_module) -> None:
        """A BudgetWarning JSONL entry is written when an agent exceeds its budget."""
        log_file = tmp_path / "activity.jsonl"

        # implementer budget is 480s; 600s exceeds it
        hook_module._check_and_log_budget(
            agent_type="implementer",
            duration_ms=600_000,  # 600 seconds
            session_id="test-session",
            log_file=log_file,
        )

        assert log_file.exists(), "Log file should have been created"
        lines = [json.loads(line) for line in log_file.read_text().strip().splitlines()]
        assert len(lines) == 1
        entry = lines[0]
        assert entry["hook"] == "BudgetWarning"
        assert entry["agent_type"] == "implementer"
        assert entry["level"] == "exceeded"
        assert entry["duration_seconds"] == pytest.approx(600.0, rel=0.01)

    def test_no_budget_warning_for_fast_agent(self, tmp_path: Path, hook_module) -> None:
        """No BudgetWarning entry is written when an agent is within budget."""
        log_file = tmp_path / "activity.jsonl"

        # implementer budget is 480s; 100s is well within budget
        hook_module._check_and_log_budget(
            agent_type="implementer",
            duration_ms=100_000,  # 100 seconds
            session_id="test-session",
            log_file=log_file,
        )

        # No entry should have been written
        assert not log_file.exists() or log_file.read_text().strip() == ""

    def test_budget_check_non_blocking(self, tmp_path: Path, hook_module) -> None:
        """Budget check never raises — it swallows all exceptions."""
        log_file = tmp_path / "broken.jsonl"
        # Make log_file a directory so writes fail
        log_file.mkdir(parents=True)

        # Should not raise even with a broken log file
        try:
            hook_module._check_and_log_budget(
                agent_type="implementer",
                duration_ms=999_999,
                session_id="test-session",
                log_file=log_file,
            )
        except Exception as exc:
            pytest.fail(f"_check_and_log_budget raised unexpectedly: {exc}")

    def test_budget_check_skipped_for_unknown_agent(self, tmp_path: Path, hook_module) -> None:
        """No BudgetWarning entry for an unknown agent type."""
        log_file = tmp_path / "activity.jsonl"

        hook_module._check_and_log_budget(
            agent_type="unknown-xyzzy-agent",
            duration_ms=999_999,
            session_id="test-session",
            log_file=log_file,
        )

        # No entry written because agent is unknown
        assert not log_file.exists() or log_file.read_text().strip() == ""
