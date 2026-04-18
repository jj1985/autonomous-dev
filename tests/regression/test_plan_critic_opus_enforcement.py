"""
Regression tests for plan-critic opus enforcement and iterative critique loop.

Issue #889: enforce opus model for plan-critic in /plan command.
Issue #890: multi-round sequential critique loop with convergence criteria.
Issue #891: convergence trap detection.
Issue #892: STEP 5 to STEP 6 transition enforcement.
Issue #893: scoring anchors for plan-critic agent.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_CMD = REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "plan.md"


class TestPlanCriticOpusEnforcement:
    def setup_method(self):
        self.content = PLAN_CMD.read_text()

    def test_step1_has_opus_model_invocation(self):
        """STEP 1 plan-critic invocation must specify model='opus'."""
        step1_section = self.content.split("### STEP 2")[0]
        assert 'model="opus"' in step1_section, (
            "STEP 1 plan-critic invocation must include model=opus"
        )

    def test_step5_has_opus_model_invocation(self):
        """STEP 5 plan-critic invocation must specify model='opus'."""
        step5_start = self.content.find("### STEP 5")
        step5_end = self.content.find("### STEP 6")
        step5_section = self.content[step5_start:step5_end]
        assert 'model="opus"' in step5_section, (
            "STEP 5 plan-critic invocation must include model=opus"
        )

    def test_step5_has_model_enforcement_note(self):
        """STEP 5 must have a prominent MODEL ENFORCEMENT instruction."""
        step5_start = self.content.find("### STEP 5")
        step5_end = self.content.find("### STEP 6")
        step5_section = self.content[step5_start:step5_end]
        assert "MODEL ENFORCEMENT" in step5_section, (
            "STEP 5 must contain a MODEL ENFORCEMENT note for plan-critic"
        )

    def test_forbidden_block_prohibits_non_opus(self):
        """plan.md must have a FORBIDDEN block covering model override in STEP 5."""
        step5_start = self.content.find("### STEP 5")
        step5_end = self.content.find("### STEP 6")
        step5_section = self.content[step5_start:step5_end]
        assert "FORBIDDEN" in step5_section, (
            "STEP 5 must contain a FORBIDDEN block for model override"
        )

    def test_plan_critic_agent_definition_uses_opus(self):
        """Cross-check: plan-critic agent definition must declare model: opus."""
        agent_path = REPO_ROOT / "plugins" / "autonomous-dev" / "agents" / "plan-critic.md"
        agent_content = agent_path.read_text()
        assert "model: opus" in agent_content, (
            "plan-critic.md agent definition must declare model: opus in frontmatter"
        )

    def test_both_invocations_present(self):
        """plan.md must have at least 2 occurrences of plan-critic subagent_type."""
        count = self.content.count('subagent_type="plan-critic"')
        assert count >= 2, (
            f"Expected at least 2 plan-critic invocations, found {count}"
        )

    # --- Issue #890: Multi-round critique loop ---

    def test_step5_has_minimum_3_rounds(self):
        """STEP 5 must specify minimum 3 rounds."""
        step5_start = self.content.find("### STEP 5")
        step5_end = self.content.find("### STEP 6")
        step5_section = self.content[step5_start:step5_end]
        assert "3 rounds" in step5_section.lower() or "minimum**: 3" in step5_section

    def test_step5_has_maximum_5_rounds(self):
        """STEP 5 must specify maximum 5 rounds."""
        step5_start = self.content.find("### STEP 5")
        step5_end = self.content.find("### STEP 6")
        step5_section = self.content[step5_start:step5_end]
        assert "5 rounds" in step5_section.lower() or "maximum**: 5" in step5_section

    def test_step5_has_convergence_criteria(self):
        """STEP 5 must have convergence criteria."""
        step5_start = self.content.find("### STEP 5")
        step5_end = self.content.find("### STEP 6")
        step5_section = self.content[step5_start:step5_end]
        assert "3.0" in step5_section, "Convergence threshold 3.0 must be specified"

    # --- Issue #891: Convergence trap detection ---

    def test_step5_has_convergence_trap_detection(self):
        """STEP 5 must have convergence trap detection."""
        step5_start = self.content.find("### STEP 5")
        step5_end = self.content.find("### STEP 6")
        step5_section = self.content[step5_start:step5_end]
        assert "Sycophantic" in step5_section or "sycophantic" in step5_section

    # --- Issue #892: STEP 5 to 6 transition gate ---

    def test_step5_to_6_transition_gate(self):
        """Transition gate between STEP 5 and STEP 6 must exist."""
        step5_end = self.content.find("### STEP 6")
        transition_area = self.content[self.content.find("### STEP 5"):step5_end]
        assert "Transition to STEP 6" in transition_area or "HARD GATE: Transition" in transition_area

    # --- Issue #893: Scoring anchors ---

    def test_plan_critic_has_scoring_anchors(self):
        """plan-critic.md must have scoring anchor examples."""
        agent_path = REPO_ROOT / "plugins" / "autonomous-dev" / "agents" / "plan-critic.md"
        agent_content = agent_path.read_text()
        assert "Scoring Anchors" in agent_content
        assert "Score 1" in agent_content
        assert "Score 5" in agent_content
