"""Spec validation tests for Issue #878: plan-critic ordering gate enforcement.

These tests validate the acceptance criteria from the spec ONLY,
testing observable behavior without knowledge of implementation details.

Acceptance criteria:
1. SEQUENTIAL_REQUIRED contains ("planner", "plan-critic") and ("plan-critic", "implementer")
2. STEP_ORDER includes "plan-critic": 3.5
3. FULL_PIPELINE_AGENTS includes "plan-critic"
4. FIX_PIPELINE_AGENTS does NOT include "plan-critic"
5. Implementer blocked if plan-critic not completed (full mode, no bypass)
6. Implementer NOT blocked in fix mode without plan-critic
7. Implementer NOT blocked when plan_critic_skipped recorded (5.5a bypass)
8. Completeness gate respects plan_critic_skipped flag
9. All existing ordering tests still pass (verified by running existing suite)
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"

# Add lib to path so we can import the modules under test
sys.path.insert(0, str(LIB_DIR))


@pytest.fixture(autouse=True)
def _clean_sys_path():
    """Ensure LIB_DIR is on sys.path for every test, clean up after."""
    if str(LIB_DIR) not in sys.path:
        sys.path.insert(0, str(LIB_DIR))
    yield


@pytest.fixture
def unique_session_id():
    """Generate a unique session ID per test to avoid state file collisions."""
    return f"spec878-{time.time_ns()}"


@pytest.fixture(autouse=True)
def _clean_env():
    """Remove bypass env vars before each test."""
    old_skip = os.environ.pop("SKIP_AGENT_COMPLETENESS_GATE", None)
    yield
    if old_skip is not None:
        os.environ["SKIP_AGENT_COMPLETENESS_GATE"] = old_skip


# ---------------------------------------------------------------------------
# Criterion 1: SEQUENTIAL_REQUIRED contains plan-critic pairs
# ---------------------------------------------------------------------------


def test_spec_878_1_sequential_required_planner_to_plan_critic():
    """SEQUENTIAL_REQUIRED must contain ("planner", "plan-critic")."""
    from agent_ordering_gate import SEQUENTIAL_REQUIRED

    assert ("planner", "plan-critic") in SEQUENTIAL_REQUIRED


def test_spec_878_1_sequential_required_plan_critic_to_implementer():
    """SEQUENTIAL_REQUIRED must contain ("plan-critic", "implementer")."""
    from agent_ordering_gate import SEQUENTIAL_REQUIRED

    assert ("plan-critic", "implementer") in SEQUENTIAL_REQUIRED


# ---------------------------------------------------------------------------
# Criterion 2: STEP_ORDER includes plan-critic at 3.5
# ---------------------------------------------------------------------------


def test_spec_878_2_step_order_plan_critic():
    """STEP_ORDER must map plan-critic to 3.5."""
    from agent_ordering_gate import STEP_ORDER

    assert "plan-critic" in STEP_ORDER
    assert STEP_ORDER["plan-critic"] == 3.5


# ---------------------------------------------------------------------------
# Criterion 3: FULL_PIPELINE_AGENTS includes plan-critic
# ---------------------------------------------------------------------------


def test_spec_878_3_full_pipeline_includes_plan_critic():
    """FULL_PIPELINE_AGENTS must include plan-critic."""
    from agent_ordering_gate import FULL_PIPELINE_AGENTS

    assert "plan-critic" in FULL_PIPELINE_AGENTS


# ---------------------------------------------------------------------------
# Criterion 4: FIX_PIPELINE_AGENTS does NOT include plan-critic
# ---------------------------------------------------------------------------


def test_spec_878_4_fix_pipeline_excludes_plan_critic():
    """FIX_PIPELINE_AGENTS must NOT include plan-critic."""
    from agent_ordering_gate import FIX_PIPELINE_AGENTS

    assert "plan-critic" not in FIX_PIPELINE_AGENTS


# ---------------------------------------------------------------------------
# Criterion 5: Implementer blocked without plan-critic in full mode
# ---------------------------------------------------------------------------


def test_spec_878_5_implementer_blocked_without_plan_critic_full_mode():
    """In full mode, implementer must be blocked if plan-critic has not completed."""
    from agent_ordering_gate import check_ordering_prerequisites

    completed = {"planner", "researcher-local", "researcher"}
    result = check_ordering_prerequisites(
        "implementer",
        completed,
        pipeline_mode="full",
    )
    assert not result.passed
    assert "plan-critic" in result.missing_agents


# ---------------------------------------------------------------------------
# Criterion 6: Implementer NOT blocked in fix mode without plan-critic
# ---------------------------------------------------------------------------


def test_spec_878_6_implementer_allowed_in_fix_mode():
    """In fix mode, implementer must NOT be blocked by missing plan-critic."""
    from agent_ordering_gate import check_ordering_prerequisites

    completed: set = set()
    result = check_ordering_prerequisites(
        "implementer",
        completed,
        pipeline_mode="fix",
    )
    assert result.passed


# ---------------------------------------------------------------------------
# Criterion 7: Implementer NOT blocked when plan_critic_skipped (5.5a bypass)
# ---------------------------------------------------------------------------


def test_spec_878_7_plan_critic_skipped_removes_from_required():
    """When plan_critic_skipped=True, plan-critic is removed from required agents."""
    from agent_ordering_gate import get_required_agents

    required = get_required_agents("full", plan_critic_skipped=True)
    assert "plan-critic" not in required

    required_normal = get_required_agents("full")
    assert "plan-critic" in required_normal


def test_spec_878_7_ordering_gate_bypass_with_plan_critic_skipped():
    """check_ordering_prerequisites must pass for implementer when plan_critic_skipped=True
    and only planner has completed (plan-critic not completed)."""
    from agent_ordering_gate import check_ordering_prerequisites

    result = check_ordering_prerequisites(
        "implementer",
        {"planner"},
        pipeline_mode="full",
        plan_critic_skipped=True,
    )
    assert result.passed, f"Implementer should pass with plan_critic_skipped=True but got: {result.reason}"


# ---------------------------------------------------------------------------
# Criterion 8: Completeness gate respects plan_critic_skipped flag
# ---------------------------------------------------------------------------


def test_spec_878_8_completeness_gate_passes_with_plan_critic_skipped(unique_session_id):
    """verify_pipeline_agent_completions must pass when plan_critic_skipped is
    recorded and all other required agents have completed."""
    from pipeline_completion_state import (
        clear_session,
        record_agent_completion,
        record_plan_critic_skipped,
        verify_pipeline_agent_completions,
    )
    from agent_ordering_gate import get_required_agents

    session_id = unique_session_id

    try:
        record_plan_critic_skipped(session_id)

        required = get_required_agents("full", plan_critic_skipped=True)
        assert "plan-critic" not in required

        for agent in required:
            record_agent_completion(session_id, agent)

        passed, completed, missing = verify_pipeline_agent_completions(
            session_id, "full"
        )
        assert passed, f"Completeness gate failed with missing={missing}"
        assert len(missing) == 0
    finally:
        clear_session(session_id)


def test_spec_878_8_completeness_gate_fails_without_plan_critic_or_skip(unique_session_id):
    """verify_pipeline_agent_completions must fail when plan-critic is not completed
    and plan_critic_skipped is NOT recorded."""
    from pipeline_completion_state import (
        clear_session,
        record_agent_completion,
        verify_pipeline_agent_completions,
    )
    from agent_ordering_gate import FULL_PIPELINE_AGENTS

    session_id = unique_session_id

    try:
        for agent in FULL_PIPELINE_AGENTS:
            if agent != "plan-critic":
                record_agent_completion(session_id, agent)

        passed, completed, missing = verify_pipeline_agent_completions(
            session_id, "full"
        )
        assert not passed, "Completeness gate should fail without plan-critic"
        assert "plan-critic" in missing
    finally:
        clear_session(session_id)


def test_spec_878_8_plan_critic_skipped_roundtrip(unique_session_id):
    """record_plan_critic_skipped and get_plan_critic_skipped must round-trip."""
    from pipeline_completion_state import (
        clear_session,
        get_plan_critic_skipped,
        record_plan_critic_skipped,
    )

    session_id = unique_session_id

    try:
        assert not get_plan_critic_skipped(session_id)
        record_plan_critic_skipped(session_id)
        assert get_plan_critic_skipped(session_id)
    finally:
        clear_session(session_id)


# ---------------------------------------------------------------------------
# Cross-check: pipeline_intent_validator constants
# ---------------------------------------------------------------------------


def test_spec_878_2_pipeline_intent_validator_step_order():
    """pipeline_intent_validator.STEP_ORDER must also include plan-critic at 3.5."""
    from pipeline_intent_validator import STEP_ORDER

    assert "plan-critic" in STEP_ORDER
    assert STEP_ORDER["plan-critic"] == 3.5


def test_spec_878_1_pipeline_intent_validator_sequential_required():
    """pipeline_intent_validator.SEQUENTIAL_REQUIRED must contain plan-critic pairs."""
    from pipeline_intent_validator import SEQUENTIAL_REQUIRED

    assert ("planner", "plan-critic") in SEQUENTIAL_REQUIRED
    assert ("plan-critic", "implementer") in SEQUENTIAL_REQUIRED
