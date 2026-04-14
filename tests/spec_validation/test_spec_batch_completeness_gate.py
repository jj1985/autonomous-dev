"""Spec validation tests for Issue #853: Batch agent completeness gate.

Tests verify behavioral acceptance criteria ONLY -- no implementation details.

Criteria tested:
1. In batch mode, the gate checks ALL issue keys in the state file
2. Per-issue research_skipped flags are respected
3. In non-batch mode, behavior is single-issue check
4. Gate fails open on any error
5. SKIP_AGENT_COMPLETENESS_GATE=1 bypass works in both modes
6. Block messages in batch mode include which issues miss which agents
"""

import json
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

# Add lib to path so we can import pipeline_completion_state and agent_ordering_gate
_lib_dir = str(
    Path(__file__).resolve().parent.parent.parent
    / "plugins"
    / "autonomous-dev"
    / "lib"
)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

import pipeline_completion_state as pcs
from agent_ordering_gate import FULL_PIPELINE_AGENTS, get_required_agents


def _unique_session() -> str:
    """Generate a unique session ID for test isolation."""
    return f"spec-test-{uuid.uuid4().hex[:12]}"


def _populate_state(session_id: str, completions: dict, research_skipped: dict | None = None):
    """Write a state file directly to set up test preconditions.

    Args:
        session_id: Session identifier.
        completions: Dict mapping issue keys (str) to dict of agent->bool.
        research_skipped: Dict mapping issue keys (str) to bool.
    """
    from datetime import datetime, timezone

    state = {
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "validation_mode": "sequential",
        "completions": completions,
        "prompt_baselines": {},
    }
    if research_skipped:
        state["research_skipped"] = research_skipped
    pcs._write_state(session_id, state)


@pytest.fixture(autouse=True)
def _cleanup_env():
    """Ensure SKIP_AGENT_COMPLETENESS_GATE is not set unless explicitly tested."""
    old = os.environ.pop("SKIP_AGENT_COMPLETENESS_GATE", None)
    yield
    if old is not None:
        os.environ["SKIP_AGENT_COMPLETENESS_GATE"] = old
    else:
        os.environ.pop("SKIP_AGENT_COMPLETENESS_GATE", None)


@pytest.fixture()
def session_id():
    """Provide a unique session ID and clean up state file after test."""
    sid = _unique_session()
    yield sid
    pcs.clear_session(sid)


# ============================================================================
# Criterion 1: In batch mode, the gate checks ALL issue keys in the state file
# ============================================================================


class TestCriterion1AllIssuesChecked:
    """The gate must check ALL issue keys, not just one."""

    def test_spec_batch_completeness_1_all_issues_checked(self, session_id):
        """Given a state file with 3 issues, verify_pipeline_agent_completions
        is called for each -- demonstrated by each issue returning its own
        pass/fail result independently.
        """
        full_agents = {agent: True for agent in FULL_PIPELINE_AGENTS}
        incomplete_agents = {agent: True for agent in FULL_PIPELINE_AGENTS if agent != "reviewer"}

        # Issue 100: complete, Issue 200: incomplete (missing reviewer), Issue 300: complete
        _populate_state(session_id, {
            "100": full_agents,
            "200": incomplete_agents,
            "300": full_agents,
        })

        # Issue 100 should pass
        passed_100, _, missing_100 = pcs.verify_pipeline_agent_completions(
            session_id, "full", issue_number=100
        )
        assert passed_100 is True
        assert len(missing_100) == 0

        # Issue 200 should fail (missing reviewer)
        passed_200, _, missing_200 = pcs.verify_pipeline_agent_completions(
            session_id, "full", issue_number=200
        )
        assert passed_200 is False
        assert "reviewer" in missing_200

        # Issue 300 should pass
        passed_300, _, missing_300 = pcs.verify_pipeline_agent_completions(
            session_id, "full", issue_number=300
        )
        assert passed_300 is True
        assert len(missing_300) == 0

    def test_spec_batch_completeness_1b_multiple_issues_can_fail(self, session_id):
        """Multiple issues can each independently fail with different missing agents."""
        agents_missing_reviewer = {
            agent: True for agent in FULL_PIPELINE_AGENTS if agent != "reviewer"
        }
        agents_missing_planner = {
            agent: True for agent in FULL_PIPELINE_AGENTS if agent != "planner"
        }

        _populate_state(session_id, {
            "10": agents_missing_reviewer,
            "20": agents_missing_planner,
        })

        passed_10, _, missing_10 = pcs.verify_pipeline_agent_completions(
            session_id, "full", issue_number=10
        )
        passed_20, _, missing_20 = pcs.verify_pipeline_agent_completions(
            session_id, "full", issue_number=20
        )

        assert passed_10 is False
        assert "reviewer" in missing_10
        assert passed_20 is False
        assert "planner" in missing_20


# ============================================================================
# Criterion 2: Per-issue research_skipped flags are respected
# ============================================================================


class TestCriterion2ResearchSkipped:
    """An issue with research_skipped=true must not require researcher agents."""

    def test_spec_batch_completeness_2_research_skipped_excludes_researchers(self, session_id):
        """Issue with research_skipped=true passes without researcher/researcher-local."""
        # All agents EXCEPT researcher and researcher-local
        agents_no_research = {
            agent: True
            for agent in FULL_PIPELINE_AGENTS
            if agent not in ("researcher", "researcher-local")
        }

        _populate_state(
            session_id,
            {"42": agents_no_research},
            research_skipped={"42": True},
        )

        passed, completed, missing = pcs.verify_pipeline_agent_completions(
            session_id, "full", issue_number=42
        )
        assert passed is True, f"Should pass with research_skipped=True, but missing: {missing}"

    def test_spec_batch_completeness_2b_research_not_skipped_requires_researchers(self, session_id):
        """Issue WITHOUT research_skipped must include researcher agents."""
        agents_no_research = {
            agent: True
            for agent in FULL_PIPELINE_AGENTS
            if agent not in ("researcher", "researcher-local")
        }

        _populate_state(
            session_id,
            {"42": agents_no_research},
            # No research_skipped flag
        )

        passed, _, missing = pcs.verify_pipeline_agent_completions(
            session_id, "full", issue_number=42
        )
        assert passed is False
        # At least one researcher agent should be missing
        assert missing & {"researcher", "researcher-local"}

    def test_spec_batch_completeness_2c_per_issue_research_skipped_independent(self, session_id):
        """research_skipped is per-issue: issue 10 skipped, issue 20 not."""
        agents_no_research = {
            agent: True
            for agent in FULL_PIPELINE_AGENTS
            if agent not in ("researcher", "researcher-local")
        }
        full_agents = {agent: True for agent in FULL_PIPELINE_AGENTS}

        _populate_state(
            session_id,
            {"10": agents_no_research, "20": agents_no_research},
            research_skipped={"10": True},  # Only issue 10 skipped
        )

        # Issue 10: research skipped -> should pass without researchers
        passed_10, _, missing_10 = pcs.verify_pipeline_agent_completions(
            session_id, "full", issue_number=10
        )
        assert passed_10 is True, f"Issue 10 should pass (research skipped), missing: {missing_10}"

        # Issue 20: research NOT skipped -> should fail without researchers
        passed_20, _, missing_20 = pcs.verify_pipeline_agent_completions(
            session_id, "full", issue_number=20
        )
        assert passed_20 is False, "Issue 20 should fail (research not skipped)"


# ============================================================================
# Criterion 3: Non-batch mode behavior (single-issue check)
# ============================================================================


class TestCriterion3NonBatchMode:
    """In non-batch mode, verify_pipeline_agent_completions works for issue 0."""

    def test_spec_batch_completeness_3_nonbatch_single_issue(self, session_id):
        """Non-batch mode uses issue_number=0 and checks a single issue."""
        full_agents = {agent: True for agent in FULL_PIPELINE_AGENTS}
        _populate_state(session_id, {"0": full_agents})

        passed, completed, missing = pcs.verify_pipeline_agent_completions(
            session_id, "full", issue_number=0
        )
        assert passed is True
        assert len(missing) == 0

    def test_spec_batch_completeness_3b_nonbatch_missing_agent_fails(self, session_id):
        """Non-batch mode fails when an agent is missing for issue 0."""
        incomplete = {
            agent: True for agent in FULL_PIPELINE_AGENTS if agent != "security-auditor"
        }
        _populate_state(session_id, {"0": incomplete})

        passed, _, missing = pcs.verify_pipeline_agent_completions(
            session_id, "full", issue_number=0
        )
        assert passed is False
        assert "security-auditor" in missing


# ============================================================================
# Criterion 4: Gate fails open on any error
# ============================================================================


class TestCriterion4FailOpen:
    """The gate must return (True, set(), set()) on any error (exception)."""

    def test_spec_batch_completeness_4_exception_fails_open(self, session_id, monkeypatch):
        """If get_completed_agents raises an unexpected exception, gate fails open."""
        _populate_state(session_id, {"5": {"implementer": True}})

        # Force an exception inside the try block
        def raise_error(*args, **kwargs):
            raise RuntimeError("simulated failure")

        monkeypatch.setattr(pcs, "get_completed_agents", raise_error)

        passed, completed, missing = pcs.verify_pipeline_agent_completions(
            session_id, "full", issue_number=5
        )
        assert passed is True
        assert completed == set()
        assert missing == set()

    def test_spec_batch_completeness_4b_import_error_fails_open(self, session_id, monkeypatch):
        """If agent_ordering_gate import fails and file is missing, gate fails open."""
        _populate_state(session_id, {"5": {"implementer": True}})

        # Force get_research_skipped to raise, simulating a deeper failure
        def raise_error(*args, **kwargs):
            raise OSError("permission denied")

        monkeypatch.setattr(pcs, "get_research_skipped", raise_error)

        passed, completed, missing = pcs.verify_pipeline_agent_completions(
            session_id, "full", issue_number=5
        )
        assert passed is True
        assert completed == set()
        assert missing == set()


# ============================================================================
# Criterion 5: SKIP_AGENT_COMPLETENESS_GATE=1 bypass
# ============================================================================


class TestCriterion5SkipBypass:
    """SKIP_AGENT_COMPLETENESS_GATE=1 must bypass the gate."""

    def test_spec_batch_completeness_5_skip_env_bypasses_batch(self, session_id):
        """With SKIP_AGENT_COMPLETENESS_GATE=1, even incomplete issues pass."""
        # Set up incomplete state
        _populate_state(session_id, {"50": {"implementer": True}})

        os.environ["SKIP_AGENT_COMPLETENESS_GATE"] = "1"
        passed, _, _ = pcs.verify_pipeline_agent_completions(
            session_id, "full", issue_number=50
        )
        assert passed is True

    def test_spec_batch_completeness_5b_skip_env_bypasses_nonbatch(self, session_id):
        """With SKIP_AGENT_COMPLETENESS_GATE=1, non-batch incomplete also passes."""
        _populate_state(session_id, {"0": {"implementer": True}})

        os.environ["SKIP_AGENT_COMPLETENESS_GATE"] = "1"
        passed, _, _ = pcs.verify_pipeline_agent_completions(
            session_id, "full", issue_number=0
        )
        assert passed is True

    def test_spec_batch_completeness_5c_skip_env_true_string(self, session_id):
        """SKIP_AGENT_COMPLETENESS_GATE=true also works."""
        _populate_state(session_id, {"0": {"implementer": True}})

        os.environ["SKIP_AGENT_COMPLETENESS_GATE"] = "true"
        passed, _, _ = pcs.verify_pipeline_agent_completions(
            session_id, "full", issue_number=0
        )
        assert passed is True


# ============================================================================
# Criterion 6: Block messages include specific issues and missing agents
# ============================================================================


class TestCriterion6BlockMessageContent:
    """Block messages must identify which issues are missing which agents."""

    def test_spec_batch_completeness_6_block_message_format(self, session_id):
        """Simulate batch check and verify failure messages include issue + agent detail."""
        agents_missing_reviewer = {
            agent: True for agent in FULL_PIPELINE_AGENTS if agent != "reviewer"
        }

        _populate_state(session_id, {
            "100": agents_missing_reviewer,
            "200": {agent: True for agent in FULL_PIPELINE_AGENTS},
        })

        # Simulate what the hook does: iterate issues, collect failures
        state = pcs._read_state(session_id)
        completions = state.get("completions", {})
        failures = []
        for issue_key in completions:
            if issue_key == "0":
                continue
            try:
                issue_num = int(issue_key)
            except (ValueError, TypeError):
                continue
            passed, completed, missing = pcs.verify_pipeline_agent_completions(
                session_id, "full", issue_number=issue_num
            )
            if not passed:
                failures.append(
                    f"#{issue_num}: missing {', '.join(sorted(missing))}"
                )

        # Must have exactly one failure (issue 100)
        assert len(failures) == 1
        # The failure message must mention issue 100 and "reviewer"
        assert "#100" in failures[0]
        assert "reviewer" in failures[0]

    def test_spec_batch_completeness_6b_multiple_issues_in_message(self, session_id):
        """When multiple issues fail, each gets its own entry in failures."""
        agents_missing_reviewer = {
            agent: True for agent in FULL_PIPELINE_AGENTS if agent != "reviewer"
        }
        agents_missing_planner = {
            agent: True for agent in FULL_PIPELINE_AGENTS if agent != "planner"
        }

        _populate_state(session_id, {
            "10": agents_missing_reviewer,
            "20": agents_missing_planner,
        })

        state = pcs._read_state(session_id)
        completions = state.get("completions", {})
        failures = []
        for issue_key in completions:
            if issue_key == "0":
                continue
            try:
                issue_num = int(issue_key)
            except (ValueError, TypeError):
                continue
            passed, completed, missing = pcs.verify_pipeline_agent_completions(
                session_id, "full", issue_number=issue_num
            )
            if not passed:
                failures.append(
                    f"#{issue_num}: missing {', '.join(sorted(missing))}"
                )

        assert len(failures) == 2
        failure_text = "; ".join(failures)
        assert "#10" in failure_text
        assert "#20" in failure_text
        assert "reviewer" in failure_text
        assert "planner" in failure_text
