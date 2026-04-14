"""Spec validation tests for Issue #856: Root Cause Analysis HARD GATE for --fix pipeline.

Validates acceptance criteria:
1. implementer.md contains "HARD GATE: Root Cause Analysis" section with FORBIDDEN list
2. implementer.md frontmatter includes `debugging-workflow` in skills list
3. implement-fix.md STEP F3 prompt requires debugging-workflow methodology
4. implement-fix.md coordinator checks for `## Root Cause Analysis` in output before proceeding
5. Absent root cause section triggers re-invocation (max 1 retry, then BLOCK)
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTER_MD = PROJECT_ROOT / "plugins/autonomous-dev/agents/implementer.md"
IMPLEMENT_FIX_MD = PROJECT_ROOT / "plugins/autonomous-dev/commands/implement-fix.md"


@pytest.fixture(scope="module")
def implementer_content() -> str:
    """Read implementer.md content."""
    assert IMPLEMENTER_MD.exists(), f"implementer.md not found at {IMPLEMENTER_MD}"
    return IMPLEMENTER_MD.read_text()


@pytest.fixture(scope="module")
def fix_content() -> str:
    """Read implement-fix.md content."""
    assert IMPLEMENT_FIX_MD.exists(), f"implement-fix.md not found at {IMPLEMENT_FIX_MD}"
    return IMPLEMENT_FIX_MD.read_text()


class TestSpecCriterion1HardGateSection:
    """AC1: implementer.md contains HARD GATE: Root Cause Analysis section with FORBIDDEN list."""

    def test_spec_856_1_hard_gate_heading_exists(self, implementer_content: str):
        """implementer.md MUST contain a heading with 'HARD GATE' and 'Root Cause Analysis'."""
        assert re.search(
            r"^##\s+HARD GATE:.*Root Cause Analysis",
            implementer_content,
            re.MULTILINE,
        ), "No '## HARD GATE: Root Cause Analysis' heading found in implementer.md"

    def test_spec_856_1_forbidden_list_in_section(self, implementer_content: str):
        """The HARD GATE section MUST include a FORBIDDEN list."""
        # Find the section start
        match = re.search(
            r"^##\s+HARD GATE:.*Root Cause Analysis.*?\n",
            implementer_content,
            re.MULTILINE,
        )
        assert match, "HARD GATE: Root Cause Analysis section not found"

        # Extract text from section start to next ## heading
        section_start = match.start()
        next_heading = re.search(
            r"^## ", implementer_content[section_start + 1:], re.MULTILINE
        )
        if next_heading:
            section_text = implementer_content[
                section_start : section_start + 1 + next_heading.start()
            ]
        else:
            section_text = implementer_content[section_start:]

        assert "FORBIDDEN" in section_text, (
            "HARD GATE: Root Cause Analysis section must contain a FORBIDDEN list"
        )
        # Verify there are actual forbidden items (lines with MUST NOT)
        forbidden_items = re.findall(r"MUST NOT", section_text)
        assert len(forbidden_items) >= 1, (
            "FORBIDDEN list must contain at least one 'MUST NOT' prohibition"
        )

    def test_spec_856_1_required_output_elements(self, implementer_content: str):
        """The section MUST specify required output elements for root cause analysis."""
        match = re.search(
            r"^##\s+HARD GATE:.*Root Cause Analysis.*?\n",
            implementer_content,
            re.MULTILINE,
        )
        assert match, "HARD GATE: Root Cause Analysis section not found"
        section_start = match.start()
        next_heading = re.search(
            r"^## ", implementer_content[section_start + 1:], re.MULTILINE
        )
        if next_heading:
            section_text = implementer_content[
                section_start : section_start + 1 + next_heading.start()
            ]
        else:
            section_text = implementer_content[section_start:]

        # Must mention required elements: root cause statement, mechanism chain, 5 Whys, category
        assert "root cause statement" in section_text.lower(), (
            "Section must require a root cause statement"
        )
        assert "mechanism chain" in section_text.lower(), (
            "Section must require a mechanism chain"
        )
        assert "5 whys" in section_text.lower(), (
            "Section must require 5 Whys analysis"
        )
        assert "root cause category" in section_text.lower(), (
            "Section must require a root cause category"
        )


class TestSpecCriterion2SkillsFrontmatter:
    """AC2: implementer.md frontmatter includes debugging-workflow in skills list."""

    def test_spec_856_2_debugging_workflow_in_skills(self, implementer_content: str):
        """The frontmatter skills list MUST include debugging-workflow."""
        # Extract frontmatter between --- markers
        frontmatter_match = re.match(
            r"^---\n(.*?)\n---", implementer_content, re.DOTALL
        )
        assert frontmatter_match, "No YAML frontmatter found in implementer.md"
        frontmatter = frontmatter_match.group(1)

        # Find skills line
        skills_match = re.search(r"skills:\s*\[([^\]]+)\]", frontmatter)
        assert skills_match, "No skills list found in frontmatter"
        skills_text = skills_match.group(1)

        skills = [s.strip() for s in skills_text.split(",")]
        assert "debugging-workflow" in skills, (
            f"debugging-workflow not found in skills list: {skills}"
        )


class TestSpecCriterion3FixModeDebuggingMethodology:
    """AC3: implement-fix.md STEP F3 prompt requires debugging-workflow methodology."""

    def test_spec_856_3_step_f3_references_debugging_methodology(self, fix_content: str):
        """STEP F3 prompt MUST reference debugging-workflow methodology."""
        # Find STEP F3 section
        f3_match = re.search(r"STEP F3", fix_content)
        assert f3_match, "STEP F3 not found in implement-fix.md"

        # Extract from STEP F3 to next major step (F3.5 or F4)
        f3_start = f3_match.start()
        next_step = re.search(
            r"(?:STEP F3\.5|STEP F4|^## Step F4)",
            fix_content[f3_start + 10:],
            re.MULTILINE,
        )
        if next_step:
            f3_text = fix_content[f3_start : f3_start + 10 + next_step.start()]
        else:
            f3_text = fix_content[f3_start:]

        # Must reference debugging methodology elements
        assert "5 whys" in f3_text.lower() or "5 Whys" in f3_text, (
            "STEP F3 must reference 5 Whys technique from debugging-workflow"
        )
        assert "debugging-workflow" in f3_text.lower() or "debugging-workflow" in f3_text, (
            "STEP F3 must reference debugging-workflow skill"
        )


class TestSpecCriterion4CoordinatorRootCauseCheck:
    """AC4: implement-fix.md coordinator checks for ## Root Cause Analysis in output."""

    def test_spec_856_4_root_cause_analysis_check_exists(self, fix_content: str):
        """implement-fix.md MUST check for literal '## Root Cause Analysis' in implementer output."""
        assert "## Root Cause Analysis" in fix_content, (
            "implement-fix.md must reference '## Root Cause Analysis' for output checking"
        )

    def test_spec_856_4_check_happens_after_step_f3(self, fix_content: str):
        """The root cause check MUST happen after STEP F3 implementation."""
        f3_pos = fix_content.find("STEP F3")
        rca_gate_pos = fix_content.find("Root Cause Analysis Output Gate")
        if rca_gate_pos == -1:
            # Alternative: look for the check pattern after F3
            rca_gate_pos = fix_content.find(
                "## Root Cause Analysis",
                f3_pos + 10 if f3_pos != -1 else 0,
            )
        assert f3_pos != -1, "STEP F3 not found"
        assert rca_gate_pos != -1, "Root Cause Analysis gate/check not found after STEP F3"
        assert rca_gate_pos > f3_pos, (
            "Root Cause Analysis check must appear after STEP F3"
        )

    def test_spec_856_4_gate_is_hard_gate(self, fix_content: str):
        """The root cause analysis check MUST be a HARD GATE."""
        # Find the gate section
        gate_match = re.search(
            r"HARD GATE.*Root Cause Analysis.*Output",
            fix_content,
            re.IGNORECASE,
        )
        assert gate_match, (
            "Root Cause Analysis output check must be labeled as HARD GATE"
        )


class TestSpecCriterion5RetryThenBlock:
    """AC5: Absent root cause section triggers re-invocation (max 1 retry, then BLOCK)."""

    def test_spec_856_5_re_invocation_on_absence(self, fix_content: str):
        """implement-fix.md MUST specify re-invocation when root cause section is absent."""
        # Find the gate section
        gate_pos = fix_content.find("Root Cause Analysis Output Gate")
        if gate_pos == -1:
            gate_pos = fix_content.find("HARD GATE: Root Cause Analysis")
            # Use the one in implement-fix.md (after STEP F3)
            f3_pos = fix_content.find("STEP F3")
            if f3_pos != -1:
                gate_pos = fix_content.find(
                    "Root Cause Analysis", f3_pos + 10
                )

        assert gate_pos != -1, "Root Cause Analysis gate not found in implement-fix.md"

        # Extract gate section text (until next ## or ### heading)
        remaining = fix_content[gate_pos:]
        next_heading = re.search(r"\n#{2,3}\s+(?!Root Cause)", remaining[1:])
        if next_heading:
            gate_text = remaining[: next_heading.start() + 1]
        else:
            gate_text = remaining

        # Must mention re-invocation
        assert re.search(
            r"re-invoke|re-invoc|retry|reinvoke",
            gate_text,
            re.IGNORECASE,
        ), "Gate must specify re-invocation when root cause analysis is absent"

    def test_spec_856_5_block_after_failed_retry(self, fix_content: str):
        """implement-fix.md MUST BLOCK after retry fails to produce root cause analysis."""
        # Find the gate section in implement-fix.md
        gate_pos = fix_content.find("Root Cause Analysis Output Gate")
        if gate_pos == -1:
            f3_pos = fix_content.find("STEP F3")
            if f3_pos != -1:
                gate_pos = fix_content.find("Root Cause Analysis", f3_pos + 10)

        assert gate_pos != -1, "Root Cause Analysis gate not found"

        remaining = fix_content[gate_pos:]

        # Must mention BLOCK after retry failure
        assert re.search(
            r"BLOCK", remaining[:2000]
        ), "Gate must specify BLOCK after retry failure"

    def test_spec_856_5_forbidden_proceeding_without_section(self, fix_content: str):
        """implement-fix.md MUST have FORBIDDEN rule against proceeding without the section."""
        gate_pos = fix_content.find("Root Cause Analysis Output Gate")
        if gate_pos == -1:
            f3_pos = fix_content.find("STEP F3")
            if f3_pos != -1:
                gate_pos = fix_content.find("Root Cause Analysis", f3_pos + 10)

        assert gate_pos != -1, "Root Cause Analysis gate not found"

        # Look for FORBIDDEN section near the gate
        # Use the next ### heading as boundary (not STEP references which may appear inline)
        remaining = fix_content[gate_pos:]
        next_heading = re.search(r"\n###\s+(?!HARD GATE: Root Cause)", remaining[1:])
        if next_heading:
            gate_text = remaining[: next_heading.start() + 1]
        else:
            gate_text = remaining[:3000]

        assert "FORBIDDEN" in gate_text, (
            "Root Cause Analysis gate must include FORBIDDEN rules"
        )
        # The FORBIDDEN list must prohibit proceeding without the root cause section
        # Extract the full FORBIDDEN block (from FORBIDDEN to the end of the gate section)
        forbidden_pos = gate_text.find("FORBIDDEN")
        forbidden_text = gate_text[forbidden_pos:]
        assert re.search(
            r"[Pp]roceeding.*without.*Root Cause",
            forbidden_text,
            re.DOTALL,
        ), "FORBIDDEN list must prohibit proceeding without the root cause analysis section"
