"""
Tests for plan-critic skip state in pipeline_completion_state.py.

Issue #878: plan-critic added to ordering gate with conditional bypass.
"""

import sys
from pathlib import Path

import pytest

# Add lib to path
LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

from pipeline_completion_state import (
    clear_session,
    get_plan_critic_skipped,
    record_plan_critic_skipped,
)


@pytest.fixture(autouse=True)
def cleanup_session():
    """Clean up test session state before and after each test."""
    session_id = "test-plan-critic-878"
    clear_session(session_id)
    yield session_id
    clear_session(session_id)


class TestPlanCriticSkipState:
    """Tests for record_plan_critic_skipped / get_plan_critic_skipped."""

    def test_default_not_skipped(self, cleanup_session):
        """By default, plan-critic is not recorded as skipped."""
        assert get_plan_critic_skipped(cleanup_session) is False

    def test_record_and_read_skipped(self, cleanup_session):
        """After recording skip, get_plan_critic_skipped returns True."""
        record_plan_critic_skipped(cleanup_session)
        assert get_plan_critic_skipped(cleanup_session) is True

    def test_skip_with_issue_number(self, cleanup_session):
        """Skip state is per-issue: issue 42 skipped, issue 43 not."""
        record_plan_critic_skipped(cleanup_session, issue_number=42)
        assert get_plan_critic_skipped(cleanup_session, issue_number=42) is True
        assert get_plan_critic_skipped(cleanup_session, issue_number=43) is False

    def test_skip_default_issue_zero(self, cleanup_session):
        """Default issue_number=0 works independently from other issues."""
        record_plan_critic_skipped(cleanup_session, issue_number=0)
        assert get_plan_critic_skipped(cleanup_session, issue_number=0) is True
        assert get_plan_critic_skipped(cleanup_session, issue_number=1) is False

    def test_nonexistent_session_returns_false(self):
        """Unknown session returns False (not skipped)."""
        assert get_plan_critic_skipped("nonexistent-session-878") is False
