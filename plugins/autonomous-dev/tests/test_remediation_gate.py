"""
Remediation Gate Architecture Tests

Validates STEP 6.5 Remediation Gate design intent across implement.md,
reviewer.md, and implementer.md.

INTENT: Remediation gate ensures BLOCKING findings are fixed before merge.
Without a remediation loop, reviewer findings are advisory-only and the
pipeline proceeds to git operations even when critical issues exist.

See implement.md STEP 6.5
"""

from pathlib import Path

import pytest


class TestRemediationGateArchitecture:
    """
    INTENT: Remediation gate ensures BLOCKING findings are fixed before merge.

    WHY: Without a remediation loop, reviewer findings are advisory-only.
    The pipeline proceeds to git operations even when critical issues exist.
    STEP 6.5 enforces that BLOCKING findings trigger automated remediation
    with bounded retry (max 2 cycles) before filing issues and blocking.

    BREAKING CHANGE: If remediation gate removed or cycles unbounded.

    See implement.md STEP 6.5
    """

    @pytest.fixture
    def implement_cmd(self):
        path = Path(__file__).parent.parent / "commands" / "implement.md"
        return path.read_text()

    @pytest.fixture
    def reviewer_agent(self):
        path = Path(__file__).parent.parent / "agents" / "reviewer.md"
        return path.read_text()

    @pytest.fixture
    def implementer_agent(self):
        path = Path(__file__).parent.parent / "agents" / "implementer.md"
        return path.read_text()

    def test_step_6_5_exists_in_implement(self, implement_cmd):
        """Test STEP 6.5 Remediation Gate exists in implement.md."""
        assert "STEP 6.5" in implement_cmd, (
            "ARCHITECTURE VIOLATION: STEP 6.5 Remediation Gate missing from implement.md\n"
            "Remediation gate is required to enforce reviewer/security findings."
        )

    def test_step_6_5_is_hard_gate(self, implement_cmd):
        """Test STEP 6.5 is marked as a HARD GATE."""
        assert "STEP 6.5: Remediation Gate \u2014 HARD GATE" in implement_cmd, (
            "ARCHITECTURE VIOLATION: STEP 6.5 must be a HARD GATE\n"
            "Advisory remediation is not sufficient \u2014 it must block the pipeline."
        )

    def test_max_2_remediation_cycles(self, implement_cmd):
        """Test remediation loop is bounded to max 2 cycles."""
        assert "max 2 cycle" in implement_cmd.lower(), (
            "ARCHITECTURE VIOLATION: Remediation must be bounded to max 2 cycles\n"
            "Unbounded remediation loops waste tokens and can never converge."
        )

    def test_reviewer_has_blocking_warning_severity(self, reviewer_agent):
        """Test reviewer output format includes BLOCKING and WARNING severity tiers."""
        assert "BLOCKING" in reviewer_agent, (
            "ARCHITECTURE VIOLATION: Reviewer must use BLOCKING severity tier\n"
            "Without severity tiers, all findings are treated equally."
        )
        assert "WARNING" in reviewer_agent, (
            "ARCHITECTURE VIOLATION: Reviewer must use WARNING severity tier\n"
            "Without severity tiers, minor issues block the pipeline."
        )

    def test_implementer_has_remediation_mode(self, implementer_agent):
        """Test implementer agent has a Remediation Mode section."""
        assert "Remediation Mode" in implementer_agent, (
            "ARCHITECTURE VIOLATION: Implementer must support Remediation Mode\n"
            "Without remediation mode, the implementer cannot be re-invoked for targeted fixes."
        )
        assert "REMEDIATION MODE" in implementer_agent, (
            "ARCHITECTURE VIOLATION: Implementer must recognize REMEDIATION MODE prompt keyword\n"
            "This keyword triggers remediation-specific behavior."
        )

    def test_pipeline_blocks_after_2_failed_cycles(self, implement_cmd):
        """Test pipeline blocks (does not proceed to STEP 7) after 2 exhausted cycles."""
        assert "BLOCK" in implement_cmd, (
            "ARCHITECTURE VIOLATION: Pipeline must BLOCK after 2 failed remediation cycles"
        )
        assert "gh issue create" in implement_cmd, (
            "ARCHITECTURE VIOLATION: Remaining BLOCKING findings must be filed as GitHub issues\n"
            "after 2 failed remediation cycles."
        )

    def test_doc_master_excluded_from_remediation(self, implement_cmd):
        """Test doc-master is not invoked during remediation loop."""
        assert "Do NOT invoke doc-master during remediation" in implement_cmd, (
            "ARCHITECTURE VIOLATION: doc-master must be excluded from remediation loop\n"
            "Documentation updates during remediation add noise without fixing BLOCKING issues."
        )

    def test_step_8_has_remediation_precondition(self, implement_cmd):
        """Test STEP 8 requires STEP 6.5 Remediation Gate to have status PASS."""
        assert "STEP 6.5 Remediation Gate must have status PASS" in implement_cmd, (
            "ARCHITECTURE VIOLATION: STEP 8 must require STEP 6.5 PASS as precondition\n"
            "Without this, git operations can proceed despite unresolved BLOCKING findings."
        )
