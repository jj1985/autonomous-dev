"""Tests for CIA cross-repo finding routing (Issue #739)."""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CIA_AGENT = REPO_ROOT / "plugins" / "autonomous-dev" / "agents" / "continuous-improvement-analyst.md"
WORKFLOW_DOCS = REPO_ROOT / "docs" / "WORKFLOW-DISCIPLINE.md"


class TestCIAFindingRouting:
    """Verify CIA agent has cross-repo finding routing."""

    def setup_method(self):
        self.cia_content = CIA_AGENT.read_text()

    def test_has_finding_routing_section(self):
        """AC1: CIA prompt has a Finding Routing section."""
        assert re.search(r"(?i)#+\s*finding\s+routing", self.cia_content), \
            "CIA agent prompt must have a 'Finding Routing' section header"

    def test_has_routing_decision_heuristic(self):
        """AC1: Routing section has decision heuristic based on fix location."""
        assert "plugins/autonomous-dev/" in self.cia_content, \
            "CIA must reference plugins/autonomous-dev/ path for routing heuristic"
        # Should mention routing to autonomous-dev vs consumer
        assert re.search(r"(?i)(consumer|active\s+repo)", self.cia_content), \
            "CIA must mention consumer/active repo as a routing target"

    def test_has_target_repo_field(self):
        """AC2: Structured output includes target_repo field."""
        assert "target_repo" in self.cia_content, \
            "CIA output must include target_repo field"
        # Should list the valid values
        for value in ["consumer", "autonomous-dev", "both"]:
            assert value in self.cia_content, \
                f"CIA must list '{value}' as a valid target_repo value"

    def test_has_filing_commands_with_repo_flag(self):
        """AC3: CIA emits filing commands with repo flag for framework findings."""
        # Should have gh issue create with -R flag for autonomous-dev
        assert re.search(r"gh\s+issue\s+create\s+.*-R\s+akaszubski/autonomous-dev", self.cia_content) or \
               re.search(r"--repo\s+akaszubski/autonomous-dev", self.cia_content), \
            "CIA must emit gh issue create with -R akaszubski/autonomous-dev for framework findings"

    def test_has_at_least_4_routing_examples(self):
        """AC4: At least 4 routing examples in the prompt."""
        # Find the routing section and count examples
        routing_match = re.search(r"(?i)(#+\s*finding\s+routing.*?)(?=\n#+\s|\Z)", self.cia_content, re.DOTALL)
        assert routing_match, "Finding Routing section must exist"
        routing_section = routing_match.group(1)

        # Count distinct example patterns (numbered items, bullet items with arrows, etc.)
        examples = re.findall(r"(?:→|->|⟶)", routing_section)
        assert len(examples) >= 4, \
            f"Need at least 4 routing examples (with → arrows), found {len(examples)}"

    def test_workflow_docs_has_cross_repo_section(self):
        """AC5: WORKFLOW-DISCIPLINE.md has cross-repo finding routing subsection."""
        docs_content = WORKFLOW_DOCS.read_text()
        assert re.search(r"(?i)#+\s*cross-repo\s+finding\s+routing", docs_content), \
            "WORKFLOW-DISCIPLINE.md must have a 'Cross-repo finding routing' subsection"
