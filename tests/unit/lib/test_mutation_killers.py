"""Mutation-killing tests targeting boundary conditions in critical lib files.

These tests focus on conditional mutations (< vs <=, == vs !=), arithmetic
mutations, and boolean mutations that mutmut would introduce. They exercise
edge cases and off_by_one boundaries that standard tests often miss.

Implements: Issue #770 (mutation testing infrastructure)
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"

# Add lib to path for imports
sys.path.insert(0, str(LIB_DIR))


class TestPipelineStateBoundary:
    """Boundary condition tests for pipeline_state.py.

    These kill conditional mutants in step advancement and gate logic.
    """

    def test_step_sequence_index_boundary_first_step(self):
        """Boundary: first step (index 0) should have no prior step checks.

        Kills mutant: changing `STEP_SEQUENCE[:step_idx]` to `STEP_SEQUENCE[:step_idx+1]`
        which would incorrectly include the step itself in prior-step checks.
        """
        from pipeline_state import (
            Step,
            StepStatus,
            STEP_SEQUENCE,
            create_pipeline,
            can_advance,
        )

        state = create_pipeline("test-boundary-001", "test feature")
        first_step = STEP_SEQUENCE[0]
        allowed, reason = can_advance(state, first_step)
        # First step should always be advanceable (no prior steps to check)
        assert allowed is True, f"First step should be advanceable: {reason}"

    def test_can_advance_rejects_already_passed_step(self):
        """Boundary: == vs != on StepStatus.PASSED check.

        Kills mutant: changing `== StepStatus.PASSED` to `!= StepStatus.PASSED`
        would allow re-entering completed steps.
        """
        from pipeline_state import (
            Step,
            StepStatus,
            create_pipeline,
            can_advance,
            advance,
            complete_step,
        )

        state = create_pipeline("test-boundary-002", "test feature")
        # Advance and complete the first step
        state = advance(state, Step.ALIGNMENT)
        state = complete_step(state, Step.ALIGNMENT, passed=True)

        # Should NOT be able to re-enter a PASSED step
        allowed, reason = can_advance(state, Step.ALIGNMENT)
        assert allowed is False, "Should not re-enter a PASSED step"
        assert "PASSED" in reason

    def test_gate_condition_requires_passed_or_skipped_not_running(self):
        """Boundary: gate check uses `not in (PASSED, SKIPPED)`.

        Kills mutant: changing the tuple membership to include RUNNING would
        incorrectly allow advancement when prerequisites are still running.
        """
        from pipeline_state import (
            Step,
            StepStatus,
            GATE_CONDITIONS,
            create_pipeline,
            can_advance,
            advance,
            complete_step,
        )

        state = create_pipeline("test-boundary-003", "test feature")
        # Advance through steps up to just before IMPLEMENT's prerequisite
        for step in [Step.ALIGNMENT, Step.RESEARCH_CACHE, Step.RESEARCH, Step.PLAN,
                      Step.ACCEPTANCE_TESTS]:
            state = advance(state, step)
            state = complete_step(state, step, passed=True)

        # Set TDD_TESTS to RUNNING (not PASSED or SKIPPED)
        state = advance(state, Step.TDD_TESTS)
        # TDD_TESTS is now RUNNING

        # IMPLEMENT has gate condition on TDD_TESTS
        assert Step.IMPLEMENT in GATE_CONDITIONS
        assert Step.TDD_TESTS in GATE_CONDITIONS[Step.IMPLEMENT]

        allowed, reason = can_advance(state, Step.IMPLEMENT)
        assert allowed is False, "Should not advance when prerequisite is RUNNING"

    def test_run_id_validation_boundary_length(self):
        """Boundary: run_id max length is 128 chars (<=128 valid, >128 invalid).

        Kills mutant: changing `{1,128}` regex quantifier boundary.
        """
        from pipeline_state import get_state_path
        import pytest

        # Exactly 128 chars should be valid
        valid_id = "a" * 128
        path = get_state_path(valid_id)
        assert path is not None

        # 129 chars should be invalid
        invalid_id = "a" * 129
        with pytest.raises(ValueError):
            get_state_path(invalid_id)

    def test_skippable_steps_boundary(self):
        """Boundary: only specific steps are skippable.

        Kills mutant: adding or removing steps from SKIPPABLE_STEPS set.
        """
        from pipeline_state import Step, SKIPPABLE_STEPS

        # These MUST be skippable
        assert Step.RESEARCH_CACHE in SKIPPABLE_STEPS
        assert Step.ACCEPTANCE_TESTS in SKIPPABLE_STEPS
        assert Step.TDD_TESTS in SKIPPABLE_STEPS
        assert Step.HOOK_CHECK in SKIPPABLE_STEPS

        # These MUST NOT be skippable
        assert Step.ALIGNMENT not in SKIPPABLE_STEPS
        assert Step.IMPLEMENT not in SKIPPABLE_STEPS
        assert Step.VALIDATE not in SKIPPABLE_STEPS


class TestToolValidatorBoundary:
    """Boundary condition tests for tool_validator.py.

    These kill conditional mutants in whitelist/blacklist matching.
    """

    def test_empty_command_handling(self):
        """Boundary: empty string command should be denied, not crash.

        Kills mutant: removing the empty-check guard clause.
        """
        from tool_validator import ToolValidator

        validator = ToolValidator(policy={
            "bash": {"whitelist": ["pytest*"], "blacklist": ["rm*"]},
            "file_paths": {"whitelist": ["*"], "blacklist": []},
            "agents": {},
        })
        result = validator.validate_bash_command("")
        assert result.approved is False, "Empty command should be denied"

    def test_injection_pattern_carriage_return_boundary(self):
        """Boundary: carriage return injection (exact match vs partial).

        Kills mutant: weakening the \\r pattern match.
        """
        from tool_validator import COMPILED_INJECTION_PATTERNS

        # The carriage return pattern must detect \r
        cr_patterns = [(p, r) for p, r in COMPILED_INJECTION_PATTERNS if r == "carriage_return"]
        assert len(cr_patterns) >= 1, "Carriage return injection pattern must exist"

        pattern, reason = cr_patterns[0]
        assert pattern.search("echo hello\rmalicious") is not None
        assert pattern.search("echo hello") is None

    def test_validation_result_security_risk_default_false(self):
        """Boundary: security_risk defaults to False (not True).

        Kills mutant: changing default `security_risk: bool = False` to True.
        """
        from tool_validator import ValidationResult

        result = ValidationResult(approved=True, reason="test")
        assert result.security_risk is False, "Default security_risk should be False"


class TestSettingsGeneratorBoundary:
    """Boundary condition tests for settings_generator.py.

    These kill conditional mutants in pattern validation and deny list checks.
    """

    def test_validate_none_settings_returns_invalid(self):
        """Boundary: None input vs empty dict input.

        Kills mutant: removing the `is None` check before the `isinstance` check.
        """
        from settings_generator import validate_permission_patterns

        result = validate_permission_patterns(None)
        assert result.valid is False
        assert result.needs_fix is True
        assert len(result.issues) >= 1

    def test_validate_empty_deny_list_is_error(self):
        """Boundary: empty deny list should be detected as error.

        Kills mutant: changing `len(deny_list) == 0` to `len(deny_list) != 0`.
        """
        from settings_generator import validate_permission_patterns

        settings = {
            "permissions": {
                "allow": ["Read", "Write"],
                "deny": [],
            }
        }
        result = validate_permission_patterns(settings)
        # Empty deny list should be flagged
        assert result.valid is False or any(
            issue.issue_type == "empty_deny_list" for issue in result.issues
        ), "Empty deny list should be detected as an issue"

    def test_bash_wildcard_detected_as_error_severity(self):
        """Boundary: Bash(*) must be severity 'error', not 'warning'.

        Kills mutant: changing severity from "error" to "warning".
        """
        from settings_generator import validate_permission_patterns

        settings = {
            "permissions": {
                "allow": ["Bash(*)"],
                "deny": ["Bash(rm:-rf*)"],
            }
        }
        result = validate_permission_patterns(settings)
        wildcard_issues = [i for i in result.issues if i.pattern == "Bash(*)"]
        assert len(wildcard_issues) >= 1, "Bash(*) should be detected"
        assert wildcard_issues[0].severity == "error", (
            f"Bash(*) should be severity 'error', got '{wildcard_issues[0].severity}'"
        )

    def test_bash_colon_wildcard_detected_as_warning_severity(self):
        """Boundary: Bash(:*) must be severity 'warning', not 'error'.

        Kills mutant: changing severity from "warning" to "error".
        """
        from settings_generator import validate_permission_patterns

        settings = {
            "permissions": {
                "allow": ["Bash(:*)"],
                "deny": ["Bash(rm:-rf*)"],
            }
        }
        result = validate_permission_patterns(settings)
        colon_issues = [i for i in result.issues if i.pattern == "Bash(:*)"]
        assert len(colon_issues) >= 1, "Bash(:*) should be detected"
        assert colon_issues[0].severity == "warning", (
            f"Bash(:*) should be severity 'warning', got '{colon_issues[0].severity}'"
        )

    def test_default_deny_list_contains_critical_entries(self):
        """Boundary: deny list must include critical security patterns.

        Kills mutant: removing entries from DEFAULT_DENY_LIST.
        """
        from settings_generator import DEFAULT_DENY_LIST

        # Critical entries that must be present
        critical_patterns = [
            "Bash(rm:-rf*)",
            "Bash(sudo:*)",
            "Bash(eval:*)",
            "Bash(chmod:*)",
        ]
        for pattern in critical_patterns:
            assert pattern in DEFAULT_DENY_LIST, (
                f"Critical deny pattern missing: {pattern}"
            )
