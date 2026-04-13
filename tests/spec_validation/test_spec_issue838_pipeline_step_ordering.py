"""Spec validation tests for Issue #838: Pipeline step ordering enforcement.

These tests validate the acceptance criteria from the spec ONLY,
testing observable behavior without knowledge of implementation details.

Acceptance criteria:
1. pytest-gate is a virtual agent prerequisite for STEP 10 agents
   (reviewer, security-auditor, doc-master) -- blocked until pytest gate passes.
2. reviewer->security-auditor always requires reviewer COMPLETION even in parallel mode.
3. SKIP_PYTEST_GATE=1 escape hatch bypasses the pytest gate requirement.
4. Coordinator can record pytest gate pass/fail via pipeline_completion_state.
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
    return f"spec838-{time.time_ns()}"


@pytest.fixture(autouse=True)
def _clean_env():
    """Remove SKIP_PYTEST_GATE from environment before each test."""
    old = os.environ.pop("SKIP_PYTEST_GATE", None)
    yield
    if old is not None:
        os.environ["SKIP_PYTEST_GATE"] = old
    else:
        os.environ.pop("SKIP_PYTEST_GATE", None)


# ---------------------------------------------------------------------------
# Criterion 1: pytest-gate blocks reviewer, security-auditor, doc-master
# ---------------------------------------------------------------------------


class TestPytestGateBlocksStep10Agents:
    """STEP 10 agents (reviewer, security-auditor, doc-master) are blocked
    until pytest-gate has completed."""

    def test_spec_838_1a_reviewer_blocked_without_pytest_gate(self):
        """Reviewer is blocked when pytest-gate has not completed."""
        from agent_ordering_gate import check_ordering_prerequisites

        completed = {"planner", "implementer"}  # pytest-gate missing
        result = check_ordering_prerequisites(
            "reviewer", completed, validation_mode="sequential"
        )
        assert not result.passed
        assert "pytest-gate" in result.missing_agents

    def test_spec_838_1b_security_auditor_blocked_without_pytest_gate(self):
        """Security-auditor is blocked when pytest-gate has not completed."""
        from agent_ordering_gate import check_ordering_prerequisites

        completed = {"planner", "implementer", "reviewer"}  # pytest-gate missing
        result = check_ordering_prerequisites(
            "security-auditor", completed, validation_mode="sequential"
        )
        assert not result.passed
        assert "pytest-gate" in result.missing_agents

    def test_spec_838_1c_doc_master_blocked_without_pytest_gate(self):
        """Doc-master is blocked when pytest-gate has not completed."""
        from agent_ordering_gate import check_ordering_prerequisites

        completed = {"planner", "implementer"}  # pytest-gate missing
        result = check_ordering_prerequisites(
            "doc-master", completed, validation_mode="sequential"
        )
        assert not result.passed
        assert "pytest-gate" in result.missing_agents

    def test_spec_838_1d_reviewer_allowed_with_pytest_gate(self):
        """Reviewer is allowed when pytest-gate has completed."""
        from agent_ordering_gate import check_ordering_prerequisites

        completed = {"planner", "implementer", "pytest-gate"}
        result = check_ordering_prerequisites(
            "reviewer", completed, validation_mode="sequential"
        )
        assert result.passed

    def test_spec_838_1e_all_step10_allowed_with_pytest_gate(self):
        """All STEP 10 agents pass when pytest-gate is in completed set."""
        from agent_ordering_gate import check_ordering_prerequisites

        completed = {"planner", "implementer", "pytest-gate", "reviewer"}
        for agent in ("reviewer", "security-auditor", "doc-master"):
            result = check_ordering_prerequisites(
                agent, completed, validation_mode="sequential"
            )
            assert result.passed, f"{agent} should be allowed but was blocked: {result.reason}"


# ---------------------------------------------------------------------------
# Criterion 1 (supplemental): pytest-gate is in ordering constants
# ---------------------------------------------------------------------------


class TestPytestGateInOrderingConstants:
    """pytest-gate appears in STEP_ORDER and SEQUENTIAL_REQUIRED."""

    def test_spec_838_1f_pytest_gate_in_step_order(self):
        """pytest-gate has an entry in STEP_ORDER between implementer and reviewer."""
        from agent_ordering_gate import STEP_ORDER

        assert "pytest-gate" in STEP_ORDER
        assert STEP_ORDER["pytest-gate"] > STEP_ORDER["implementer"]
        assert STEP_ORDER["pytest-gate"] < STEP_ORDER["reviewer"]

    def test_spec_838_1g_pytest_gate_prerequisite_pairs_exist(self):
        """SEQUENTIAL_REQUIRED contains pytest-gate -> reviewer/security-auditor/doc-master."""
        from agent_ordering_gate import SEQUENTIAL_REQUIRED

        expected_pairs = [
            ("pytest-gate", "reviewer"),
            ("pytest-gate", "security-auditor"),
            ("pytest-gate", "doc-master"),
        ]
        for pair in expected_pairs:
            assert pair in SEQUENTIAL_REQUIRED, f"Missing pair: {pair}"

    def test_spec_838_1h_pytest_gate_in_all_pipeline_agent_sets(self):
        """pytest-gate appears in FULL, LIGHT, and FIX pipeline agent sets."""
        from agent_ordering_gate import (
            FIX_PIPELINE_AGENTS,
            FULL_PIPELINE_AGENTS,
            LIGHT_PIPELINE_AGENTS,
        )

        assert "pytest-gate" in FULL_PIPELINE_AGENTS
        assert "pytest-gate" in LIGHT_PIPELINE_AGENTS
        assert "pytest-gate" in FIX_PIPELINE_AGENTS


# ---------------------------------------------------------------------------
# Criterion 2: reviewer->security-auditor always enforced
# ---------------------------------------------------------------------------


class TestReviewerSecurityAuditorAlwaysEnforced:
    """reviewer->security-auditor is always required, even in parallel mode."""

    def test_spec_838_2a_reviewer_required_before_security_auditor_sequential(self):
        """In sequential mode, security-auditor requires reviewer completion."""
        from agent_ordering_gate import check_ordering_prerequisites

        # implementer + pytest-gate done, but reviewer not done
        completed = {"planner", "implementer", "pytest-gate"}
        result = check_ordering_prerequisites(
            "security-auditor", completed, validation_mode="sequential"
        )
        assert not result.passed
        assert "reviewer" in result.missing_agents

    def test_spec_838_2b_reviewer_required_before_security_auditor_parallel(self):
        """In parallel mode, security-auditor still requires reviewer completion
        (reviewer->security-auditor is NOT mode-dependent)."""
        from agent_ordering_gate import check_ordering_prerequisites

        completed = {"planner", "implementer", "pytest-gate"}
        launched = {"planner", "implementer", "pytest-gate", "reviewer"}
        result = check_ordering_prerequisites(
            "security-auditor",
            completed,
            validation_mode="parallel",
            launched_agents=launched,
        )
        # reviewer is a CORE prerequisite (not mode-dependent), so it must be completed
        assert not result.passed
        assert "reviewer" in result.missing_agents

    def test_spec_838_2c_mode_dependent_pairs_empty(self):
        """MODE_DEPENDENT_PAIRS is empty -- reviewer->security-auditor moved to always-enforced."""
        from agent_ordering_gate import MODE_DEPENDENT_PAIRS

        assert len(MODE_DEPENDENT_PAIRS) == 0

    def test_spec_838_2d_reviewer_security_auditor_in_sequential_required(self):
        """The (reviewer, security-auditor) pair is in SEQUENTIAL_REQUIRED."""
        from agent_ordering_gate import SEQUENTIAL_REQUIRED

        assert ("reviewer", "security-auditor") in SEQUENTIAL_REQUIRED


# ---------------------------------------------------------------------------
# Criterion 3: SKIP_PYTEST_GATE=1 escape hatch
# ---------------------------------------------------------------------------


class TestSkipPytestGateEscapeHatch:
    """SKIP_PYTEST_GATE=1 environment variable bypasses the pytest gate."""

    def test_spec_838_3a_skip_env_var_allows_reviewer(self):
        """With SKIP_PYTEST_GATE=1, reviewer is not blocked by missing pytest-gate."""
        from pipeline_completion_state import get_pytest_gate_passed

        os.environ["SKIP_PYTEST_GATE"] = "1"
        # Even without any state, get_pytest_gate_passed returns True
        assert get_pytest_gate_passed("nonexistent-session-id") is True

    def test_spec_838_3b_skip_env_var_values(self):
        """SKIP_PYTEST_GATE accepts '1', 'true', 'yes' (case-insensitive)."""
        from pipeline_completion_state import get_pytest_gate_passed

        for value in ("1", "true", "True", "TRUE", "yes", "Yes", "YES"):
            os.environ["SKIP_PYTEST_GATE"] = value
            assert get_pytest_gate_passed("nonexistent") is True, f"Failed for value={value!r}"

    def test_spec_838_3c_skip_env_var_not_set_returns_false(self):
        """Without SKIP_PYTEST_GATE, get_pytest_gate_passed returns False on empty session."""
        from pipeline_completion_state import get_pytest_gate_passed

        os.environ.pop("SKIP_PYTEST_GATE", None)
        assert get_pytest_gate_passed("nonexistent-session-id") is False


# ---------------------------------------------------------------------------
# Criterion 4: Coordinator records pytest gate
# ---------------------------------------------------------------------------


class TestRecordPytestGate:
    """Coordinator can record pytest gate pass/fail."""

    def test_spec_838_4a_record_and_retrieve_pytest_gate(self, unique_session_id):
        """record_pytest_gate_passed makes get_pytest_gate_passed return True."""
        from pipeline_completion_state import (
            clear_session,
            get_pytest_gate_passed,
            record_pytest_gate_passed,
        )

        try:
            record_pytest_gate_passed(unique_session_id)
            assert get_pytest_gate_passed(unique_session_id) is True
        finally:
            clear_session(unique_session_id)

    def test_spec_838_4b_pytest_gate_appears_in_completed_agents(self, unique_session_id):
        """After recording, pytest-gate appears in get_completed_agents."""
        from pipeline_completion_state import (
            clear_session,
            get_completed_agents,
            record_pytest_gate_passed,
        )

        try:
            record_pytest_gate_passed(unique_session_id)
            completed = get_completed_agents(unique_session_id)
            assert "pytest-gate" in completed
        finally:
            clear_session(unique_session_id)

    def test_spec_838_4c_pytest_gate_not_passed_when_recorded_as_failed(self, unique_session_id):
        """record_pytest_gate_passed(passed=False) does NOT make the gate pass."""
        from pipeline_completion_state import (
            clear_session,
            get_pytest_gate_passed,
            record_pytest_gate_passed,
        )

        try:
            record_pytest_gate_passed(unique_session_id, passed=False)
            assert get_pytest_gate_passed(unique_session_id) is False
        finally:
            clear_session(unique_session_id)

    def test_spec_838_4d_pytest_gate_per_issue(self, unique_session_id):
        """pytest-gate can be recorded per issue number."""
        from pipeline_completion_state import (
            clear_session,
            get_pytest_gate_passed,
            record_pytest_gate_passed,
        )

        try:
            record_pytest_gate_passed(unique_session_id, issue_number=100)
            assert get_pytest_gate_passed(unique_session_id, issue_number=100) is True
            # Different issue should not have the gate
            assert get_pytest_gate_passed(unique_session_id, issue_number=200) is False
        finally:
            clear_session(unique_session_id)


# ---------------------------------------------------------------------------
# Criterion (supplemental): Intent validator mirrors constants
# ---------------------------------------------------------------------------


class TestIntentValidatorMirrorsConstants:
    """pipeline_intent_validator has matching ordering constants."""

    def test_spec_838_5a_intent_validator_has_pytest_gate_in_step_order(self):
        """pipeline_intent_validator.STEP_ORDER contains pytest-gate."""
        from pipeline_intent_validator import STEP_ORDER

        assert "pytest-gate" in STEP_ORDER

    def test_spec_838_5b_intent_validator_has_pytest_gate_pairs(self):
        """pipeline_intent_validator.SEQUENTIAL_REQUIRED has pytest-gate pairs."""
        from pipeline_intent_validator import SEQUENTIAL_REQUIRED

        expected_pairs = [
            ("pytest-gate", "reviewer"),
            ("pytest-gate", "security-auditor"),
            ("pytest-gate", "doc-master"),
        ]
        for pair in expected_pairs:
            assert pair in SEQUENTIAL_REQUIRED, f"Missing pair in intent_validator: {pair}"
