"""Spec validation tests for Issue #802: Agent completeness gate.

These tests validate the acceptance criteria from the spec ONLY,
testing observable behavior without knowledge of implementation details.

Acceptance criteria:
1. Git commit blocked when required agents missing (full-mode pipeline)
2. Git commit allowed when all required agents completed
3. Git commit allowed when research legitimately skipped + researchers absent
4. Non-pipeline commits not affected (fail-open on missing state)
5. Escape hatch SKIP_AGENT_COMPLETENESS_GATE=1 works
6. Gate fails open on errors (missing state, corrupt data)
7. STEP 9.5 in implement.md references research_skipped tracking
8. STEP 3.5 includes record_research_skipped instruction
9. Unit tests (>=12) and regression tests (>=6) exist
10. Existing test suite passes
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
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
    return f"spec802-{time.time_ns()}"


@pytest.fixture
def state_file_cleanup(unique_session_id):
    """Clean up state file after test."""
    from pipeline_completion_state import clear_session

    yield unique_session_id
    clear_session(unique_session_id)


@pytest.fixture(autouse=True)
def _clean_env():
    """Remove escape hatch env vars before each test."""
    old = os.environ.pop("SKIP_AGENT_COMPLETENESS_GATE", None)
    yield
    if old is not None:
        os.environ["SKIP_AGENT_COMPLETENESS_GATE"] = old
    else:
        os.environ.pop("SKIP_AGENT_COMPLETENESS_GATE", None)


# ---------------------------------------------------------------------------
# Criterion 1: Git commit BLOCKED when required agents missing
# ---------------------------------------------------------------------------


def test_spec_issue802_1_blocked_when_researchers_missing(state_file_cleanup):
    """Full-mode pipeline blocks when researcher-local, researcher missing."""
    from pipeline_completion_state import (
        record_agent_completion,
        verify_pipeline_agent_completions,
    )

    session_id = state_file_cleanup
    # Record only some agents -- omit researcher-local, researcher
    for agent in ["planner", "implementer", "reviewer", "security-auditor", "doc-master"]:
        record_agent_completion(session_id, agent, issue_number=0, success=True)

    passed, completed, missing = verify_pipeline_agent_completions(
        session_id, "full", issue_number=0
    )

    assert passed is False
    assert "researcher-local" in missing or "researcher" in missing


def test_spec_issue802_1b_blocked_when_security_auditor_missing(state_file_cleanup):
    """Full-mode pipeline blocks when security-auditor missing."""
    from pipeline_completion_state import (
        record_agent_completion,
        verify_pipeline_agent_completions,
    )

    session_id = state_file_cleanup
    for agent in ["researcher-local", "researcher", "planner", "implementer", "reviewer", "doc-master"]:
        record_agent_completion(session_id, agent, issue_number=0, success=True)

    passed, completed, missing = verify_pipeline_agent_completions(
        session_id, "full", issue_number=0
    )

    assert passed is False
    assert "security-auditor" in missing


# ---------------------------------------------------------------------------
# Criterion 2: Git commit ALLOWED when all required agents completed
# ---------------------------------------------------------------------------


def test_spec_issue802_2_allowed_when_all_agents_completed(state_file_cleanup):
    """Full-mode pipeline allows commit when all required agents completed."""
    from pipeline_completion_state import (
        record_agent_completion,
        verify_pipeline_agent_completions,
    )

    session_id = state_file_cleanup
    full_agents = [
        "researcher-local",
        "researcher",
        "planner",
        "plan-critic",
        "implementer",
        "pytest-gate",
        "reviewer",
        "security-auditor",
        "doc-master",
    ]
    for agent in full_agents:
        record_agent_completion(session_id, agent, issue_number=0, success=True)

    passed, completed, missing = verify_pipeline_agent_completions(
        session_id, "full", issue_number=0
    )

    assert passed is True
    assert len(missing) == 0


# ---------------------------------------------------------------------------
# Criterion 3: Git commit ALLOWED when research legitimately skipped
# ---------------------------------------------------------------------------


def test_spec_issue802_3_allowed_when_research_skipped(state_file_cleanup):
    """When research is skipped, commit allowed without researcher agents."""
    from pipeline_completion_state import (
        record_agent_completion,
        record_research_skipped,
        verify_pipeline_agent_completions,
    )

    session_id = state_file_cleanup
    record_research_skipped(session_id, issue_number=0)

    # Record all agents EXCEPT researchers (which were legitimately skipped)
    for agent in ["planner", "plan-critic", "implementer", "pytest-gate", "reviewer", "security-auditor", "doc-master"]:
        record_agent_completion(session_id, agent, issue_number=0, success=True)

    passed, completed, missing = verify_pipeline_agent_completions(
        session_id, "full", issue_number=0
    )

    assert passed is True
    assert "researcher-local" not in missing
    assert "researcher" not in missing


# ---------------------------------------------------------------------------
# Criterion 4: Non-pipeline commits NOT affected
# The hook only invokes the agent completeness check when _is_pipeline_active()
# returns True. We verify the hook wiring includes this guard.
# ---------------------------------------------------------------------------


def test_spec_issue802_4_nonpipeline_commits_not_affected():
    """Hook only checks agent completeness when pipeline is active.

    The agent completeness gate at the hook level (unified_pre_tool.py)
    must be guarded by a pipeline-active check so non-pipeline commits
    are not affected.
    """
    hook_path = (
        REPO_ROOT / "plugins" / "autonomous-dev" / "hooks" / "unified_pre_tool.py"
    )
    content = hook_path.read_text()

    # Find the comment marker for the #802 wiring in the main dispatch
    # (not the function definition)
    marker = "# Issue #802: Pipeline agent completeness gate"
    idx = content.find(marker)
    assert idx != -1, "Hook must contain Issue #802 wiring comment"

    # Look at the 1000 chars after the marker for the pipeline-active guard
    context = content[idx : idx + 1000]
    assert "_is_pipeline_active()" in context, (
        "Agent completeness gate must be guarded by _is_pipeline_active() check"
    )


# ---------------------------------------------------------------------------
# Criterion 5: Escape hatch SKIP_AGENT_COMPLETENESS_GATE=1 works
# ---------------------------------------------------------------------------


def test_spec_issue802_5_escape_hatch_bypasses_gate(state_file_cleanup):
    """SKIP_AGENT_COMPLETENESS_GATE=1 allows commit even with missing agents."""
    from pipeline_completion_state import (
        record_agent_completion,
        verify_pipeline_agent_completions,
    )

    session_id = state_file_cleanup
    # Record only one agent -- many missing
    record_agent_completion(session_id, "planner", issue_number=0, success=True)

    os.environ["SKIP_AGENT_COMPLETENESS_GATE"] = "1"

    passed, completed, missing = verify_pipeline_agent_completions(
        session_id, "full", issue_number=0
    )

    assert passed is True
    assert completed == set()
    assert missing == set()


# ---------------------------------------------------------------------------
# Criterion 6: Gate fails open on errors
# The function has a broad except Exception -> (True, set(), set()) for
# import failures and unexpected errors. The hook also wraps the call in
# try/except. We test both layers.
# ---------------------------------------------------------------------------


def test_spec_issue802_6a_function_fails_open_on_exception(state_file_cleanup, monkeypatch):
    """verify_pipeline_agent_completions returns (True, set(), set()) when
    get_completed_agents raises an unexpected error."""
    import pipeline_completion_state as pcs

    # Force an exception inside the function
    def _broken_get(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(pcs, "get_completed_agents", _broken_get)

    session_id = state_file_cleanup
    passed, completed, missing = pcs.verify_pipeline_agent_completions(
        session_id, "full", issue_number=0
    )

    assert passed is True
    assert completed == set()
    assert missing == set()


def test_spec_issue802_6b_hook_fails_open_on_errors():
    """Hook wraps agent completeness check in try/except for fail-open."""
    hook_path = (
        REPO_ROOT / "plugins" / "autonomous-dev" / "hooks" / "unified_pre_tool.py"
    )
    content = hook_path.read_text()

    # Find the Issue #802 block
    idx = content.find("Issue #802")
    assert idx != -1

    # Look for the try/except pattern around the agent completeness check
    context = content[idx : idx + 1000]
    assert "except Exception" in context, (
        "Hook must wrap agent completeness gate in try/except for fail-open"
    )
    # Verify the except block contains pass or fail-open comment
    assert "Fail-open" in context or "pass" in context


# ---------------------------------------------------------------------------
# Criterion 7: STEP 9.5 references research_skipped tracking
# ---------------------------------------------------------------------------


def test_spec_issue802_7_step_9_5_references_research_skipped():
    """implement.md STEP 9.5 mentions research_skipped or agent completeness."""
    implement_md = REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement.md"
    content = implement_md.read_text()

    # Find STEP 9.5 section
    assert "STEP 9.5" in content, "STEP 9.5 must exist in implement.md"

    # Find content around STEP 9.5 -- it should reference agent completeness
    step_9_5_idx = content.index("STEP 9.5")
    # Look at the surrounding 2000 chars for relevant references
    context = content[step_9_5_idx : step_9_5_idx + 2000]

    assert (
        "research_skipped" in context
        or "research skipped" in context.lower()
        or "agent completeness" in context.lower()
        or "verify_pipeline_agent_completions" in context
    ), "STEP 9.5 must reference research_skipped tracking or agent completeness"


# ---------------------------------------------------------------------------
# Criterion 8: STEP 3.5 includes record_research_skipped instruction
# ---------------------------------------------------------------------------


def test_spec_issue802_8_step_3_5_includes_record_research_skipped():
    """implement.md STEP 3.5 (Fully-Specified Change Detection) includes record_research_skipped."""
    implement_md = REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement.md"
    content = implement_md.read_text()

    # Find the STEP 3.5 that is about Fully-Specified Change Detection
    marker = "### STEP 3.5"
    assert marker in content, "STEP 3.5 heading must exist in implement.md"

    step_3_5_idx = content.index(marker)
    context = content[step_3_5_idx : step_3_5_idx + 2000]

    assert "record_research_skipped" in context, (
        "STEP 3.5 must include record_research_skipped instruction"
    )


# ---------------------------------------------------------------------------
# Criterion 9: Unit tests (>=12) and regression tests (>=6) exist
# ---------------------------------------------------------------------------


def test_spec_issue802_9_unit_tests_exist():
    """At least 12 unit tests exist for agent completeness."""
    unit_test_file = (
        REPO_ROOT / "tests" / "unit" / "lib" / "test_pipeline_completion_state_agent_completeness.py"
    )
    assert unit_test_file.exists(), "Unit test file must exist"

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(unit_test_file), "--co", "-q"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    # Parse "N tests collected" from output
    output = result.stdout + result.stderr
    import re

    match = re.search(r"(\d+) tests? collected", output)
    assert match is not None, f"Could not determine test count from output: {output}"
    count = int(match.group(1))
    assert count >= 12, f"Expected >=12 unit tests, found {count}"


def test_spec_issue802_9b_regression_tests_exist():
    """At least 6 regression tests exist for agent completeness."""
    regression_test_file = (
        REPO_ROOT / "tests" / "regression" / "test_issue_802_agent_completeness_gate.py"
    )
    assert regression_test_file.exists(), "Regression test file must exist"

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(regression_test_file), "--co", "-q"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    output = result.stdout + result.stderr
    import re

    match = re.search(r"(\d+) tests? collected", output)
    assert match is not None, f"Could not determine test count from output: {output}"
    count = int(match.group(1))
    assert count >= 6, f"Expected >=6 regression tests, found {count}"


# ---------------------------------------------------------------------------
# Criterion 10: Existing test suite passes
# ---------------------------------------------------------------------------


def test_spec_issue802_10a_unit_tests_pass():
    """Unit tests for agent completeness all pass."""
    unit_test_file = (
        REPO_ROOT / "tests" / "unit" / "lib" / "test_pipeline_completion_state_agent_completeness.py"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(unit_test_file), "-v", "--tb=short"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=120,
    )
    assert result.returncode == 0, (
        f"Unit tests failed (exit code {result.returncode}):\n{result.stdout}\n{result.stderr}"
    )


def test_spec_issue802_10b_regression_tests_pass():
    """Regression tests for agent completeness all pass."""
    regression_test_file = (
        REPO_ROOT / "tests" / "regression" / "test_issue_802_agent_completeness_gate.py"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(regression_test_file), "-v", "--tb=short"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=120,
    )
    assert result.returncode == 0, (
        f"Regression tests failed (exit code {result.returncode}):\n{result.stdout}\n{result.stderr}"
    )
