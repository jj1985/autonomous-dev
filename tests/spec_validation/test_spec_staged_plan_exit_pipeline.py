"""Spec validation tests for Staged Plan-Exit Pipeline.

Validates acceptance criteria:
1. plan_mode_exit_detector writes "stage": "plan_exited" in the marker file
2. plan_mode_exit_detector outputs a systemMessage mentioning plan-critic
3. unified_prompt_validator blocks /implement (without --skip-review) when stage=plan_exited
4. unified_prompt_validator allows /implement --skip-review at any stage (consumes marker)
5. unified_prompt_validator allows questions (ending with ?) at any stage
6. unified_prompt_validator allows /implement, /create-issue, /plan-to-issues when stage=critique_done
7. unified_session_tracker advances stage from plan_exited to critique_done when plan-critic fires
8. Old markers without stage field treated as critique_done (backward compat)
9. All existing test patterns still pass (no broken tests from changes)
10. At least 19 new/modified tests cover the 2-state behavior
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = PROJECT_ROOT / "plugins" / "autonomous-dev" / "hooks"

# Add hooks to path for direct import
sys.path.insert(0, str(HOOKS_DIR))

from plan_mode_exit_detector import main as detector_main, MARKER_PATH
from unified_prompt_validator import _check_plan_mode_enforcement, PLAN_MODE_EXIT_MARKER
from unified_session_tracker import _advance_plan_mode_stage


def _write_marker(tmp_path: Path, *, stage: str = "critique_done", include_stage: bool = True) -> Path:
    """Write a plan mode exit marker file for testing.

    Args:
        tmp_path: Temp directory acting as cwd.
        stage: The stage field value.
        include_stage: Whether to include the stage field at all.

    Returns:
        Path to the created marker file.
    """
    marker_path = tmp_path / PLAN_MODE_EXIT_MARKER
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": "spec-validation-session",
    }
    if include_stage:
        marker_data["stage"] = stage
    marker_path.write_text(json.dumps(marker_data))
    return marker_path


# --------------------------------------------------------------------------
# Criterion 1: plan_mode_exit_detector writes "stage": "plan_exited"
# --------------------------------------------------------------------------

def test_spec_staged_plan_exit_1_detector_writes_plan_exited_stage(tmp_path: Path):
    """Criterion 1: ExitPlanMode marker must contain stage='plan_exited'."""
    input_data = json.dumps({"tool_name": "ExitPlanMode"})
    with (
        patch("sys.stdin") as mock_stdin,
        patch("os.getcwd", return_value=str(tmp_path)),
    ):
        mock_stdin.read.return_value = input_data
        result = detector_main()

    assert result == 0
    marker_path = tmp_path / MARKER_PATH
    assert marker_path.exists(), "Marker file was not created"
    marker_data = json.loads(marker_path.read_text())
    assert marker_data.get("stage") == "plan_exited", (
        f"Expected stage='plan_exited', got stage='{marker_data.get('stage')}'"
    )


# --------------------------------------------------------------------------
# Criterion 2: plan_mode_exit_detector outputs systemMessage mentioning plan-critic
# --------------------------------------------------------------------------

def test_spec_staged_plan_exit_2_detector_system_message_mentions_plan_critic(tmp_path: Path, capsys):
    """Criterion 2: ExitPlanMode output must contain systemMessage with plan-critic."""
    input_data = json.dumps({"tool_name": "ExitPlanMode"})
    with (
        patch("sys.stdin") as mock_stdin,
        patch("os.getcwd", return_value=str(tmp_path)),
    ):
        mock_stdin.read.return_value = input_data
        detector_main()

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert "systemMessage" in output, "Output JSON missing 'systemMessage' key"
    assert "plan-critic" in output["systemMessage"].lower(), (
        "systemMessage does not mention plan-critic"
    )


# --------------------------------------------------------------------------
# Criterion 3: validator blocks /implement (no --skip-review) at plan_exited
# --------------------------------------------------------------------------

def test_spec_staged_plan_exit_3_implement_blocked_at_plan_exited(tmp_path: Path):
    """Criterion 3: /implement without --skip-review must be blocked at plan_exited stage."""
    _write_marker(tmp_path, stage="plan_exited")
    with patch("os.getcwd", return_value=str(tmp_path)):
        result = _check_plan_mode_enforcement("/implement add authentication feature")
    assert result == 2, f"Expected block (2), got {result}"


# --------------------------------------------------------------------------
# Criterion 4: --skip-review consumes marker at any stage
# --------------------------------------------------------------------------

def test_spec_staged_plan_exit_4a_skip_review_allowed_at_plan_exited(tmp_path: Path):
    """Criterion 4a: /implement --skip-review passes and consumes marker at plan_exited."""
    marker = _write_marker(tmp_path, stage="plan_exited")
    with patch("os.getcwd", return_value=str(tmp_path)):
        result = _check_plan_mode_enforcement("/implement --skip-review add auth")
    assert result == 0, f"Expected pass (0), got {result}"
    assert not marker.exists(), "Marker should be consumed (deleted)"


def test_spec_staged_plan_exit_4b_skip_review_allowed_at_critique_done(tmp_path: Path):
    """Criterion 4b: /implement --skip-review passes and consumes marker at critique_done."""
    marker = _write_marker(tmp_path, stage="critique_done")
    with patch("os.getcwd", return_value=str(tmp_path)):
        result = _check_plan_mode_enforcement("/implement --skip-review fix login")
    assert result == 0, f"Expected pass (0), got {result}"
    assert not marker.exists(), "Marker should be consumed (deleted)"


# --------------------------------------------------------------------------
# Criterion 5: questions allowed at any stage
# --------------------------------------------------------------------------

def test_spec_staged_plan_exit_5a_question_allowed_at_plan_exited(tmp_path: Path):
    """Criterion 5a: Question prompts must pass through at plan_exited stage."""
    marker = _write_marker(tmp_path, stage="plan_exited")
    with patch("os.getcwd", return_value=str(tmp_path)):
        result = _check_plan_mode_enforcement("What should I do next?")
    assert result is None, f"Expected None (pass-through), got {result}"
    assert marker.exists(), "Marker should NOT be consumed for questions"


def test_spec_staged_plan_exit_5b_question_allowed_at_critique_done(tmp_path: Path):
    """Criterion 5b: Question prompts must pass through at critique_done stage."""
    marker = _write_marker(tmp_path, stage="critique_done")
    with patch("os.getcwd", return_value=str(tmp_path)):
        result = _check_plan_mode_enforcement("Can you explain the plan?")
    assert result is None, f"Expected None (pass-through), got {result}"
    assert marker.exists(), "Marker should NOT be consumed for questions"


# --------------------------------------------------------------------------
# Criterion 6: /implement, /create-issue, /plan-to-issues allowed at critique_done
# --------------------------------------------------------------------------

def test_spec_staged_plan_exit_6a_implement_allowed_at_critique_done(tmp_path: Path):
    """Criterion 6a: /implement must pass and consume marker at critique_done."""
    marker = _write_marker(tmp_path, stage="critique_done")
    with patch("os.getcwd", return_value=str(tmp_path)):
        result = _check_plan_mode_enforcement("/implement add authentication feature")
    assert result == 0, f"Expected pass (0), got {result}"
    assert not marker.exists(), "Marker should be consumed"


def test_spec_staged_plan_exit_6b_create_issue_allowed_at_critique_done(tmp_path: Path):
    """Criterion 6b: /create-issue must pass and consume marker at critique_done."""
    marker = _write_marker(tmp_path, stage="critique_done")
    with patch("os.getcwd", return_value=str(tmp_path)):
        result = _check_plan_mode_enforcement("/create-issue authentication feature needed")
    assert result == 0, f"Expected pass (0), got {result}"
    assert not marker.exists(), "Marker should be consumed"


def test_spec_staged_plan_exit_6c_plan_to_issues_allowed_at_critique_done(tmp_path: Path):
    """Criterion 6c: /plan-to-issues must pass and consume marker at critique_done."""
    marker = _write_marker(tmp_path, stage="critique_done")
    with patch("os.getcwd", return_value=str(tmp_path)):
        result = _check_plan_mode_enforcement("/plan-to-issues")
    assert result == 0, f"Expected pass (0), got {result}"
    assert not marker.exists(), "Marker should be consumed"


# --------------------------------------------------------------------------
# Criterion 7: stage advances from plan_exited to critique_done
# --------------------------------------------------------------------------

def test_spec_staged_plan_exit_7_stage_advances_on_plan_critic_completion(tmp_path: Path):
    """Criterion 7: _advance_plan_mode_stage must change stage from plan_exited to critique_done."""
    marker_path = tmp_path / ".claude" / "plan_mode_exit.json"
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": "spec-validation-session",
        "stage": "plan_exited",
    }
    marker_path.write_text(json.dumps(marker_data, indent=2))

    with patch("os.getcwd", return_value=str(tmp_path)):
        _advance_plan_mode_stage()

    updated = json.loads(marker_path.read_text())
    assert updated["stage"] == "critique_done", (
        f"Expected stage='critique_done' after advance, got '{updated['stage']}'"
    )


# --------------------------------------------------------------------------
# Criterion 8: old markers without stage treated as critique_done
# --------------------------------------------------------------------------

def test_spec_staged_plan_exit_8_no_stage_field_treated_as_critique_done(tmp_path: Path):
    """Criterion 8: Marker without 'stage' field must behave as critique_done."""
    marker = _write_marker(tmp_path, include_stage=False)
    with patch("os.getcwd", return_value=str(tmp_path)):
        result = _check_plan_mode_enforcement("/implement add feature")
    assert result == 0, (
        f"Expected pass (0) for stageless marker (backward compat), got {result}"
    )
    assert not marker.exists(), "Marker should be consumed"


# --------------------------------------------------------------------------
# Criterion 9: all existing test patterns still pass
# --------------------------------------------------------------------------

def test_spec_staged_plan_exit_9_existing_tests_pass():
    """Criterion 9: All existing unit tests for the 3 changed test files must pass."""
    test_files = [
        str(PROJECT_ROOT / "tests/unit/hooks/test_plan_mode_exit_detector.py"),
        str(PROJECT_ROOT / "tests/unit/hooks/test_plan_mode_enforcement.py"),
        str(PROJECT_ROOT / "tests/unit/hooks/test_plan_critic_stage_advance.py"),
    ]
    result = subprocess.run(
        [sys.executable, "-m", "pytest"] + test_files + ["-v", "--tb=short", "-q"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=60,
    )
    assert result.returncode == 0, (
        f"Existing tests failed with returncode {result.returncode}.\n"
        f"stdout:\n{result.stdout[-2000:]}\n"
        f"stderr:\n{result.stderr[-1000:]}"
    )


# --------------------------------------------------------------------------
# Criterion 10: at least 19 new/modified tests cover 2-state behavior
# --------------------------------------------------------------------------

def test_spec_staged_plan_exit_10_minimum_test_count():
    """Criterion 10: At least 19 tests must cover the 2-state staged behavior."""
    # Count tests in the 3 test files that relate to staged behavior
    test_files = [
        PROJECT_ROOT / "tests/unit/hooks/test_plan_mode_exit_detector.py",
        PROJECT_ROOT / "tests/unit/hooks/test_plan_mode_enforcement.py",
        PROJECT_ROOT / "tests/unit/hooks/test_plan_critic_stage_advance.py",
    ]

    stage_related_tests = 0
    stage_keywords = [
        "stage", "plan_exited", "critique_done", "skip_review",
        "plan_critic", "advance", "backward_compat", "system_message",
    ]

    for test_file in test_files:
        content = test_file.read_text()
        # Find all test function/method names
        import re
        test_names = re.findall(r"def (test_\w+)", content)
        for name in test_names:
            name_lower = name.lower()
            if any(kw in name_lower for kw in stage_keywords):
                stage_related_tests += 1

    assert stage_related_tests >= 19, (
        f"Expected at least 19 tests covering 2-state behavior, found {stage_related_tests}"
    )
