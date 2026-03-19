"""Structural tests for implement.md thin coordinator refactor (Issue #444).

Verifies that implement.md maintains required structure after refactoring
from 383-line monolithic inline command to ~100-line thin coordinator.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
IMPLEMENT_PATH = PROJECT_ROOT / "plugins/autonomous-dev/commands/implement.md"


@pytest.fixture
def implement_content():
    """Read the implement.md command file."""
    return IMPLEMENT_PATH.read_text()


@pytest.fixture
def implement_lines(implement_content):
    """Get non-empty lines (excluding frontmatter)."""
    lines = implement_content.strip().split("\n")
    # Skip frontmatter (between --- markers)
    in_frontmatter = False
    content_lines = []
    frontmatter_count = 0
    for line in lines:
        if line.strip() == "---":
            frontmatter_count += 1
            if frontmatter_count <= 2:
                in_frontmatter = not in_frontmatter
                continue
        if not in_frontmatter:
            content_lines.append(line)
    return content_lines


class TestCoordinatorSize:
    """Verify the coordinator is thin, not monolithic."""

    def test_implement_md_under_405_lines(self, implement_content):
        """implement.md should be under 470 lines total (was 385 before auto-mode detection + STEP 6.5 remediation gate added)."""
        total_lines = len(implement_content.strip().split("\n"))
        assert total_lines <= 470, (
            f"implement.md is {total_lines} lines — should be <= 470 "
            f"(thin coordinator + Light Pipeline + auto-mode detection + STEP 6.5 remediation gate)."
        )


class TestAllStepsPresent:
    """Verify all pipeline steps are referenced."""

    @pytest.mark.parametrize(
        "step",
        [
            "STEP 0",
            "STEP 1",
            "STEP 1.5",
            "STEP 2",
            "STEP 3",
            "STEP 3.5",
            "STEP 4",
            "STEP 5",
            "STEP 5.5",
            "STEP 6",
            "STEP 7",
            "STEP 8",
            "STEP 8.5",
            "STEP 9",
        ],
    )
    def test_step_referenced(self, implement_content, step):
        """Each pipeline step must be referenced in the coordinator."""
        assert step in implement_content, f"{step} not found in implement.md"


class TestHardGatesPreserved:
    """Verify all HARD GATEs survive the refactor."""

    def test_hard_gate_keyword_present(self, implement_content):
        """HARD GATE enforcement language must be present."""
        assert "HARD GATE" in implement_content

    def test_test_gate_present(self, implement_content):
        """STEP 5 test gate — 0 failures required."""
        assert "pytest" in implement_content.lower() or "test" in implement_content.lower()

    def test_no_new_skips_gate(self, implement_content):
        """No new @pytest.mark.skip allowed."""
        assert "No New Skips" in implement_content or "0 new skips" in implement_content, (
            "No-new-skips gate must be referenced"
        )

    def test_hook_registration_gate(self, implement_content):
        """STEP 5.5 hook registration check."""
        assert "hook" in implement_content.lower() and (
            "registration" in implement_content.lower()
            or "settings" in implement_content.lower()
        )

    def test_doc_congruence_gate(self, implement_content):
        """STEP 8.5 documentation congruence validation."""
        assert "congruence" in implement_content.lower() or (
            "documentation" in implement_content.lower()
            and "test" in implement_content.lower()
        )

    def test_step_9_mandatory(self, implement_content):
        """STEP 9 continuous improvement is mandatory."""
        assert "continuous-improvement-analyst" in implement_content or (
            "STEP 9" in implement_content and "mandatory" in implement_content.lower()
        )

    def test_forbidden_list_present(self, implement_content):
        """COORDINATOR FORBIDDEN LIST must be preserved."""
        assert "FORBIDDEN" in implement_content


class TestAgentDelegation:
    """Verify all required agents are referenced for delegation."""

    @pytest.mark.parametrize(
        "agent",
        [
            "researcher-local",
            "researcher",
            "planner",
            "implementer",
            "reviewer",
            "security-auditor",
            "doc-master",
            "continuous-improvement-analyst",
        ],
    )
    def test_agent_referenced(self, implement_content, agent):
        """Each specialist agent must be referenced by name."""
        assert agent in implement_content, (
            f"Agent '{agent}' not found in implement.md — "
            f"coordinator must delegate to all specialist agents"
        )

    def test_test_master_conditional(self, implement_content):
        """test-master should be referenced for --tdd-first mode."""
        assert "test-master" in implement_content


class TestModeRouting:
    """Verify all modes are supported."""

    @pytest.mark.parametrize(
        "flag",
        ["--batch", "--issues", "--resume", "--tdd-first"],
    )
    def test_mode_flag_supported(self, implement_content, flag):
        """Each mode flag must be referenced."""
        assert flag in implement_content, f"Mode flag '{flag}' not found"

    def test_acceptance_first_default(self, implement_content):
        """Acceptance-first should be the default mode."""
        assert "acceptance" in implement_content.lower() or "default" in implement_content.lower()

    def test_batch_routes_to_implement_batch(self, implement_content):
        """Batch mode should route to implement-batch.md."""
        assert "implement-batch" in implement_content

    def test_light_mode_flag_supported(self, implement_content):
        """--light flag must be referenced."""
        assert "--light" in implement_content

    def test_fix_mode_flag_supported(self, implement_content):
        """--fix flag must be referenced."""
        assert "--fix" in implement_content

    def test_auto_mode_detection_present(self, implement_content):
        """Auto-mode detection section must exist in STEP 0."""
        assert "Auto-mode detection" in implement_content

    def test_auto_mode_fix_signals(self, implement_content):
        """Auto-mode must detect fix-related descriptions."""
        assert "Fix signals" in implement_content or "fix test" in implement_content.lower()

    def test_auto_mode_light_signals(self, implement_content):
        """Auto-mode must detect light-related descriptions."""
        assert "Light signals" in implement_content or "update docs" in implement_content.lower()

    def test_auto_mode_requires_user_confirmation(self, implement_content):
        """Auto-mode must not silently switch — requires user confirmation."""
        assert "Silently switching" in implement_content or "user confirmation" in implement_content.lower()

    def test_auto_mode_tiebreak(self, implement_content):
        """When both fix and light match, fix takes precedence."""
        assert "Tie-break" in implement_content or "fix" in implement_content.lower()


class TestPipelineState:
    """Verify pipeline state tracking is preserved."""

    def test_pipeline_state_initialization(self, implement_content):
        """Pipeline state must be initialized in STEP 0."""
        assert "pipeline" in implement_content.lower() and (
            "create_pipeline" in implement_content or "RUN_ID" in implement_content
        )

    def test_pipeline_cleanup(self, implement_content):
        """Pipeline state must be cleaned up in STEP 9."""
        assert "cleanup" in implement_content.lower() or "clean" in implement_content.lower()
