"""Property-based tests for pipeline_state.py state machine invariants.

Tests invariants:
- create_pipeline() always produces state with all steps PENDING
- PASSED steps cannot be re-entered (advance raises ValueError)
- Non-skippable steps cannot be skipped
- Skippable steps can be skipped when PENDING
- run_id validation rejects invalid characters
- Round-trip: save_pipeline then load preserves all fields
"""

import json
import re
from pathlib import Path

import pytest
from hypothesis import example, given, settings, assume
from hypothesis import strategies as st

from pipeline_state import (
    GATE_CONDITIONS,
    SKIPPABLE_STEPS,
    STEP_SEQUENCE,
    PipelineState,
    Step,
    StepStatus,
    advance,
    can_advance,
    cleanup_pipeline,
    complete_step,
    create_pipeline,
    get_state_path,
    get_trace,
    load_pipeline,
    save_pipeline,
    skip_step,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid run IDs: alphanumeric + dashes + underscores, 1-128 chars
valid_run_id = st.from_regex(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", fullmatch=True)

# Invalid run IDs: contain disallowed characters
invalid_run_id = st.from_regex(
    r"[a-zA-Z0-9_-]*[^a-zA-Z0-9_-]+[a-zA-Z0-9_-]*", fullmatch=True
).filter(lambda s: len(s) > 0 and len(s) <= 128)

# Feature descriptions
feature_text = st.text(min_size=1, max_size=200, alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")))

# Pipeline modes
pipeline_mode = st.sampled_from(["full", "quick", "batch", "light", "fix"])

# All steps
all_steps = st.sampled_from(list(Step))

# Skippable steps
skippable_step = st.sampled_from(list(SKIPPABLE_STEPS))

# Non-skippable steps
non_skippable_steps = [s for s in Step if s not in SKIPPABLE_STEPS]
non_skippable_step = st.sampled_from(non_skippable_steps)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup(run_id: str) -> None:
    """Clean up pipeline state file if it exists."""
    try:
        path = get_state_path(run_id)
        path.unlink(missing_ok=True)
    except (ValueError, OSError):
        pass


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestCreatePipelineInvariant:
    """create_pipeline() must produce state with all steps PENDING."""

    @given(run_id=valid_run_id, feature=feature_text, mode=pipeline_mode)
    @example("run-001", "Add user auth", "full")
    @example("test_123", "Fix bug", "quick")
    @settings(max_examples=200)
    def test_all_steps_pending_on_creation(
        self, run_id: str, feature: str, mode: str
    ) -> None:
        """Every step in a newly created pipeline must be PENDING."""
        try:
            state = create_pipeline(run_id, feature, mode=mode)

            # All 13 steps must be present
            assert len(state.steps) == len(STEP_SEQUENCE)

            # Every step must be PENDING
            for step in STEP_SEQUENCE:
                assert step.value in state.steps
                assert state.steps[step.value]["status"] == StepStatus.PENDING.value

            # Metadata must be populated
            assert state.run_id == run_id
            assert state.feature == feature
            assert state.mode == mode
            assert state.created_at != ""
            assert state.updated_at != ""
        finally:
            _cleanup(run_id)


class TestPassedStepReentryInvariant:
    """PASSED steps cannot be re-entered via advance()."""

    @example("reenter-01", Step.ALIGNMENT)
    @given(run_id=valid_run_id, step=all_steps)
    @settings(max_examples=200)
    def test_advance_after_passed_raises(self, run_id: str, step: Step) -> None:
        """Calling advance() on a PASSED step always raises ValueError."""
        try:
            state = create_pipeline(run_id, "test feature")

            # Force all prior steps to PASSED so we can advance to target
            step_idx = STEP_SEQUENCE.index(step)
            for prior in STEP_SEQUENCE[:step_idx]:
                state.steps[prior.value]["status"] = StepStatus.PASSED.value

            # Advance to RUNNING then PASSED
            state = advance(state, step, status=StepStatus.RUNNING)
            state = advance(state, step, status=StepStatus.PASSED)

            # Attempting to re-enter a PASSED step must raise
            with pytest.raises(ValueError, match="already PASSED"):
                advance(state, step)
        finally:
            _cleanup(run_id)


class TestNonSkippableStepInvariant:
    """Non-skippable steps must raise ValueError when skip is attempted."""

    @given(run_id=valid_run_id, step=non_skippable_step)
    @example("skip-test-01", Step.ALIGNMENT)
    @example("skip-test-02", Step.IMPLEMENT)
    @settings(max_examples=200)
    def test_skip_non_skippable_raises(self, run_id: str, step: Step) -> None:
        """skip_step() on a non-skippable step always raises ValueError."""
        try:
            state = create_pipeline(run_id, "test feature")
            with pytest.raises(ValueError, match="not skippable"):
                skip_step(state, step, reason="testing")
        finally:
            _cleanup(run_id)


class TestSkippableStepInvariant:
    """Skippable steps can be skipped when PENDING."""

    @given(run_id=valid_run_id, step=skippable_step)
    @example("skip-ok-01", Step.RESEARCH_CACHE)
    @example("skip-ok-02", Step.TDD_TESTS)
    @settings(max_examples=200)
    def test_skip_skippable_succeeds(self, run_id: str, step: Step) -> None:
        """skip_step() on a skippable PENDING step succeeds."""
        try:
            state = create_pipeline(run_id, "test feature")

            # Skip all prior steps so we can skip the target
            step_idx = STEP_SEQUENCE.index(step)
            for prior in STEP_SEQUENCE[:step_idx]:
                if prior in SKIPPABLE_STEPS:
                    state.steps[prior.value]["status"] = StepStatus.SKIPPED.value
                else:
                    state.steps[prior.value]["status"] = StepStatus.PASSED.value

            state = skip_step(state, step, reason="property test skip")
            assert state.steps[step.value]["status"] == StepStatus.SKIPPED.value
        finally:
            _cleanup(run_id)


class TestRunIdValidation:
    """get_state_path() must reject invalid run_id characters."""

    @given(run_id=invalid_run_id)
    @example("run id with spaces")
    @example("run;injection")
    @example("../traversal")
    @example("run/slash")
    @settings(max_examples=200)
    def test_invalid_run_id_rejected(self, run_id: str) -> None:
        """Run IDs with disallowed characters always raise ValueError."""
        # Only test if it truly doesn't match the valid pattern
        if re.match(r"^[a-zA-Z0-9_-]{1,128}$", run_id):
            return
        with pytest.raises(ValueError):
            get_state_path(run_id)

    @example("valid-run-01")
    @given(run_id=valid_run_id)
    @settings(max_examples=200)
    def test_valid_run_id_accepted(self, run_id: str) -> None:
        """Valid run IDs produce a Path in /tmp."""
        path = get_state_path(run_id)
        assert str(path).startswith("/tmp/pipeline_state_")
        assert path.suffix == ".json"


class TestRoundTripInvariant:
    """save_pipeline() then load_pipeline() must preserve all fields."""

    @example("roundtrip-01", "Test feature", "full")
    @given(run_id=valid_run_id, feature=feature_text, mode=pipeline_mode)
    @settings(max_examples=100)
    def test_save_load_roundtrip(self, run_id: str, feature: str, mode: str) -> None:
        """Saving and loading a pipeline preserves run_id, feature, mode, and steps."""
        try:
            state = create_pipeline(run_id, feature, mode=mode)

            # Advance first step to add some state
            state = advance(state, Step.ALIGNMENT, status=StepStatus.RUNNING)

            save_pipeline(state)
            loaded = load_pipeline(run_id)

            assert loaded is not None
            assert loaded.run_id == state.run_id
            assert loaded.feature == state.feature
            assert loaded.mode == state.mode
            assert loaded.created_at == state.created_at
            # steps should match
            for step in STEP_SEQUENCE:
                assert loaded.steps[step.value]["status"] == state.steps[step.value]["status"]
        finally:
            _cleanup(run_id)
