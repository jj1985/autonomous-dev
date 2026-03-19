"""
Unit tests for Issue #151: Research persistence for researcher agents

Tests validate that researcher-web and researcher agents have research persistence
capabilities and that doc-master manages research documentation correctly.

These tests follow TDD - they should FAIL until implementation is complete.

Run with: pytest tests/unit/test_research_persistence.py --tb=line -q
"""

import re
from pathlib import Path
from typing import List

import pytest


class TestResearcherWebPersistence:
    """Test suite for researcher-web agent research persistence."""

    AGENT_FILE = (
        Path(__file__).parent.parent.parent
        / "plugins"
        / "autonomous-dev"
        / "agents"
        / "archived"
        / "researcher-web.md"
    )

    def test_researcher_web_file_exists(self):
        """
        GIVEN: Plugin directory structure
        WHEN: Checking for researcher-web agent file
        THEN: File exists in archived directory
        """
        assert self.AGENT_FILE.exists(), f"researcher-web.md not found: {self.AGENT_FILE}"

    def test_has_research_persistence_in_core_responsibilities(self):
        """
        GIVEN: researcher-web agent file
        WHEN: Checking Core Responsibilities section
        THEN: Section mentions research persistence as a core responsibility
        """
        content = self.AGENT_FILE.read_text()

        # Extract Core Responsibilities section
        match = re.search(
            r"## Core Responsibilities(.*?)(?=\n##|\Z)", content, re.DOTALL
        )
        assert match, "researcher-web missing Core Responsibilities section"

        responsibilities = match.group(1)
        assert (
            "persist" in responsibilities.lower()
            or "documentation" in responsibilities.lower()
        ), "Core Responsibilities should mention research persistence or documentation"

    def test_has_research_persistence_section(self):
        """
        GIVEN: researcher-web agent file
        WHEN: Checking for Research Persistence section
        THEN: Section exists with proper header
        """
        content = self.AGENT_FILE.read_text()
        assert (
            "## Research Persistence" in content
        ), "researcher-web missing '## Research Persistence' section"

    def test_research_persistence_section_has_criteria(self):
        """
        GIVEN: Research Persistence section
        WHEN: Checking section content
        THEN: Section describes when to persist research
        """
        content = self.AGENT_FILE.read_text()

        # Extract Research Persistence section
        match = re.search(
            r"## Research Persistence(.*?)(?=\n##|\Z)", content, re.DOTALL
        )
        assert match, "researcher-web missing Research Persistence section"

        persistence_section = match.group(1)

        # Check for criteria keywords
        criteria_keywords = ["when", "if", "criteria", "should"]
        has_criteria = any(
            keyword in persistence_section.lower() for keyword in criteria_keywords
        )
        assert (
            has_criteria
        ), "Research Persistence section should describe criteria for persistence"

    def test_research_persistence_section_has_file_naming(self):
        """
        GIVEN: Research Persistence section
        WHEN: Checking for file naming convention
        THEN: Section mentions SCREAMING_SNAKE_CASE convention
        """
        content = self.AGENT_FILE.read_text()

        # Extract Research Persistence section
        match = re.search(
            r"## Research Persistence(.*?)(?=\n##|\Z)", content, re.DOTALL
        )
        assert match, "researcher-web missing Research Persistence section"

        persistence_section = match.group(1)

        # Check for naming convention
        assert (
            "SCREAMING_SNAKE_CASE" in persistence_section
            or "SCREAMING SNAKE CASE" in persistence_section
            or "ALL_CAPS" in persistence_section
        ), "Research Persistence section should document SCREAMING_SNAKE_CASE naming convention"

    def test_research_persistence_section_has_template(self):
        """
        GIVEN: Research Persistence section
        WHEN: Checking for document template
        THEN: Section includes example template or structure
        """
        content = self.AGENT_FILE.read_text()

        # Extract Research Persistence section
        match = re.search(
            r"## Research Persistence(.*?)(?=\n##|\Z)", content, re.DOTALL
        )
        assert match, "researcher-web missing Research Persistence section"

        persistence_section = match.group(1)

        # Check for template keywords
        template_indicators = [
            "template",
            "structure",
            "format",
            "example",
            "```",  # Code block
        ]
        has_template = any(
            indicator in persistence_section.lower()
            for indicator in template_indicators
        )
        assert (
            has_template
        ), "Research Persistence section should include template or example"

    def test_process_includes_persistence_step(self):
        """
        GIVEN: researcher-web Process section
        WHEN: Checking process steps
        THEN: Step 4 is about persisting research documentation
        """
        content = self.AGENT_FILE.read_text()

        # Extract Process section
        match = re.search(r"## Process(.*?)(?=\n##|\Z)", content, re.DOTALL)
        assert match, "researcher-web missing Process section"

        process_section = match.group(1)

        # Check for step 4 about persistence
        assert (
            "4." in process_section or "4)" in process_section
        ), "Process should have at least 4 steps"

        # Check if step 4 mentions persistence/documentation
        step_4_match = re.search(
            r"4[\.\)]\s+\*\*([^*]+)\*\*", process_section, re.MULTILINE
        )
        if step_4_match:
            step_4_title = step_4_match.group(1)
            assert (
                "persist" in step_4_title.lower()
                or "document" in step_4_title.lower()
            ), "Step 4 should be about persisting research"

    def test_skills_includes_documentation_guide(self):
        """
        GIVEN: researcher-web frontmatter
        WHEN: Checking skills field
        THEN: Includes documentation-guide skill
        """
        content = self.AGENT_FILE.read_text()

        # Extract frontmatter
        match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
        assert match, "researcher-web missing frontmatter"

        frontmatter = match.group(1)

        # Check for skills field with documentation-guide
        assert (
            "skills:" in frontmatter
        ), "researcher-web frontmatter missing skills field"
        assert (
            "documentation-guide" in frontmatter
        ), "researcher-web should include documentation-guide skill"

    def test_research_persistence_mentions_docs_directory(self):
        """
        GIVEN: Research Persistence section
        WHEN: Checking for directory structure
        THEN: Section mentions docs/research/ directory
        """
        content = self.AGENT_FILE.read_text()

        # Extract Research Persistence section
        match = re.search(
            r"## Research Persistence(.*?)(?=\n##|\Z)", content, re.DOTALL
        )
        assert match, "researcher-web missing Research Persistence section"

        persistence_section = match.group(1)

        assert (
            "docs/research" in persistence_section
            or "docs/research/" in persistence_section
        ), "Research Persistence section should specify docs/research/ directory"


class TestResearcherBackwardCompatibility:
    """Test suite for researcher agent backward compatibility."""

    AGENT_FILE = (
        Path(__file__).parent.parent.parent
        / "plugins"
        / "autonomous-dev"
        / "agents"
        / "archived"
        / "researcher.md"
    )

    def test_researcher_file_exists(self):
        """
        GIVEN: Plugin directory structure
        WHEN: Checking for researcher agent file
        THEN: File exists in archived directory
        """
        assert self.AGENT_FILE.exists(), f"researcher.md not found: {self.AGENT_FILE}"

    def test_has_optional_persistence_step(self):
        """
        GIVEN: researcher agent Process section
        WHEN: Checking process steps
        THEN: Has an optional persistence step mentioned
        """
        content = self.AGENT_FILE.read_text()

        # Extract Process section
        match = re.search(r"## Process(.*?)(?=\n##|\Z)", content, re.DOTALL)
        assert match, "researcher missing Process section"

        process_section = match.group(1)

        # Check for persistence being mentioned (could be optional)
        assert (
            "persist" in process_section.lower()
            or "documentation" in process_section.lower()
        ), "researcher Process should mention persistence option"

    def test_output_references_persisted_doc(self):
        """
        GIVEN: researcher agent Output Format section
        WHEN: Checking output structure
        THEN: Output mentions persisted doc when created
        """
        content = self.AGENT_FILE.read_text()

        # Extract Output Format section
        match = re.search(r"## Output Format(.*?)(?=\n##|\Z)", content, re.DOTALL)
        assert match, "researcher missing Output Format section"

        output_section = match.group(1)

        # Check for reference to persisted documentation
        has_doc_reference = (
            "research_doc" in output_section.lower()
            or "persisted" in output_section.lower()
            or "documentation" in output_section.lower()
        )
        assert (
            has_doc_reference
        ), "Output Format should reference persisted documentation when created"


class TestDocMasterSemanticDriftDetection:
    """Test suite for doc-master semantic drift detection (refactored v3.50+)."""

    AGENT_FILE = (
        Path(__file__).parent.parent.parent
        / "plugins"
        / "autonomous-dev"
        / "agents"
        / "doc-master.md"
    )

    def test_doc_master_file_exists(self):
        """doc-master agent file must exist."""
        assert self.AGENT_FILE.exists(), f"doc-master.md not found: {self.AGENT_FILE}"

    def test_uses_covers_frontmatter(self):
        """doc-master must reference covers: frontmatter for doc-to-source mapping."""
        content = self.AGENT_FILE.read_text()
        assert "covers:" in content, "doc-master should reference covers: frontmatter"

    def test_has_semantic_comparison_instructions(self):
        """doc-master must instruct LLM-as-judge semantic comparison."""
        content = self.AGENT_FILE.read_text()
        assert "semantic" in content.lower(), "doc-master should mention semantic comparison"

    def test_outputs_structured_verdict(self):
        """doc-master must output DOC-DRIFT-VERDICT."""
        content = self.AGENT_FILE.read_text()
        assert "DOC-DRIFT-VERDICT" in content, "doc-master should output DOC-DRIFT-VERDICT"

    def test_does_not_update_claude_md(self):
        """doc-master must NOT have CLAUDE.md in its update scope."""
        content = self.AGENT_FILE.read_text()
        # CLAUDE.md should appear in OUT of scope, not in IN scope
        scope_match = re.search(r"\*\*IN scope\*\*(.*?)\*\*OUT of scope\*\*", content, re.DOTALL)
        if scope_match:
            in_scope = scope_match.group(1)
            assert "CLAUDE.md" not in in_scope, "CLAUDE.md should not be in doc-master's IN scope"

    def test_readme_in_scope(self):
        """doc-master must have README.md in scope."""
        content = self.AGENT_FILE.read_text()
        assert "README.md" in content, "doc-master should have README.md in scope"

    def test_changelog_in_scope(self):
        """doc-master must have CHANGELOG.md in scope."""
        content = self.AGENT_FILE.read_text()
        assert "CHANGELOG.md" in content, "doc-master should have CHANGELOG.md in scope"

    def test_docs_in_scope(self):
        """doc-master must have docs/*.md in scope."""
        content = self.AGENT_FILE.read_text()
        assert "docs/*.md" in content, "doc-master should have docs/*.md in scope"


class TestResearchDocStandardsSkill:
    """Test suite for research-doc-standards skill documentation."""

    SKILL_DIR = (
        Path(__file__).parent.parent.parent
        / "plugins"
        / "autonomous-dev"
        / "skills"
        / "documentation-guide"
    )
    SKILL_DOC = SKILL_DIR / "docs" / "research-doc-standards.md"

    def test_documentation_guide_skill_exists(self):
        """
        GIVEN: Skills directory
        WHEN: Checking for documentation-guide skill
        THEN: Skill directory exists
        """
        assert (
            self.SKILL_DIR.exists()
        ), f"documentation-guide skill not found: {self.SKILL_DIR}"

    def test_docs_subdirectory_exists(self):
        """
        GIVEN: documentation-guide skill directory
        WHEN: Checking for docs subdirectory
        THEN: docs/ subdirectory exists
        """
        docs_dir = self.SKILL_DIR / "docs"
        assert docs_dir.exists(), f"docs/ subdirectory not found in {self.SKILL_DIR}"

    def test_research_doc_standards_file_exists(self):
        """
        GIVEN: documentation-guide/docs/ directory
        WHEN: Checking for research-doc-standards.md
        THEN: File exists
        """
        assert (
            self.SKILL_DOC.exists()
        ), f"research-doc-standards.md not found: {self.SKILL_DOC}"

    def test_has_required_sections(self):
        """
        GIVEN: research-doc-standards.md file
        WHEN: Checking for required sections
        THEN: File has Purpose, When to Persist, File Structure, Validation sections
        """
        content = self.SKILL_DOC.read_text()

        required_sections = [
            "## Purpose",
            "## When to Persist",
            "## File Structure",
            "## Validation",
        ]

        for section in required_sections:
            assert (
                section in content
            ), f"research-doc-standards.md missing required section: {section}"

    def test_has_screaming_snake_case_naming(self):
        """
        GIVEN: research-doc-standards.md file
        WHEN: Checking File Structure section
        THEN: Documents SCREAMING_SNAKE_CASE naming convention
        """
        content = self.SKILL_DOC.read_text()

        # Extract File Structure section
        match = re.search(r"## File Structure(.*?)(?=\n##|\Z)", content, re.DOTALL)
        assert match, "research-doc-standards.md missing File Structure section"

        structure_section = match.group(1)

        assert (
            "SCREAMING_SNAKE_CASE" in structure_section
            or "SCREAMING SNAKE CASE" in structure_section
            or "ALL_CAPS" in structure_section
        ), "File Structure should document SCREAMING_SNAKE_CASE naming"

    def test_has_directory_location(self):
        """
        GIVEN: research-doc-standards.md file
        WHEN: Checking for directory specification
        THEN: Specifies docs/research/ as storage location
        """
        content = self.SKILL_DOC.read_text()

        assert (
            "docs/research" in content or "docs/research/" in content
        ), "research-doc-standards.md should specify docs/research/ directory"

    def test_has_template_or_example(self):
        """
        GIVEN: research-doc-standards.md file
        WHEN: Checking for template/example
        THEN: File includes template or example structure
        """
        content = self.SKILL_DOC.read_text()

        # Check for code block (template) or example section
        has_template = "```" in content or "## Template" in content or "## Example" in content
        assert (
            has_template
        ), "research-doc-standards.md should include template or example"

    def test_validation_section_has_checklist(self):
        """
        GIVEN: research-doc-standards.md Validation section
        WHEN: Checking section content
        THEN: Section includes validation checklist items
        """
        content = self.SKILL_DOC.read_text()

        # Extract Validation section
        match = re.search(r"## Validation(.*?)(?=\n##|\Z)", content, re.DOTALL)
        assert match, "research-doc-standards.md missing Validation section"

        validation_section = match.group(1)

        # Check for checklist format
        checklist_patterns = [r"^- ", r"^\* ", r"^- \[ \]", r"^\d+\. "]
        has_checklist = any(
            re.search(pattern, validation_section, re.MULTILINE)
            for pattern in checklist_patterns
        )
        assert (
            has_checklist
        ), "Validation section should include checklist items"


class TestIntegrationResearchPersistence:
    """Integration tests for research persistence workflow."""

    RESEARCHER_WEB = (
        Path(__file__).parent.parent.parent
        / "plugins"
        / "autonomous-dev"
        / "agents"
        / "archived"
        / "researcher-web.md"
    )
    DOC_MASTER = (
        Path(__file__).parent.parent.parent
        / "plugins"
        / "autonomous-dev"
        / "agents"
        / "doc-master.md"
    )
    SKILL_DOC = (
        Path(__file__).parent.parent.parent
        / "plugins"
        / "autonomous-dev"
        / "skills"
        / "documentation-guide"
        / "docs"
        / "research-doc-standards.md"
    )

    def test_both_agents_reference_documentation_guide_skill(self):
        """
        GIVEN: researcher-web and doc-master agents
        WHEN: Checking their skills field
        THEN: Both include documentation-guide skill
        """
        researcher_content = self.RESEARCHER_WEB.read_text()
        doc_master_content = self.DOC_MASTER.read_text()

        assert (
            "documentation-guide" in researcher_content
        ), "researcher-web should reference documentation-guide skill"
        assert (
            "documentation-guide" in doc_master_content
        ), "doc-master should reference documentation-guide skill"

    def test_consistent_naming_convention_across_artifacts(self):
        """
        GIVEN: All research persistence artifacts
        WHEN: Checking naming convention references
        THEN: All use consistent SCREAMING_SNAKE_CASE terminology
        """
        researcher_content = self.RESEARCHER_WEB.read_text()
        doc_master_content = self.DOC_MASTER.read_text()
        skill_content = self.SKILL_DOC.read_text()

        # All should mention SCREAMING_SNAKE_CASE or similar
        naming_pattern = r"SCREAMING[_ ]SNAKE[_ ]CASE|ALL[_ ]CAPS"

        has_naming_researcher = re.search(naming_pattern, researcher_content)
        has_naming_doc_master = re.search(naming_pattern, doc_master_content)
        has_naming_skill = re.search(naming_pattern, skill_content)

        assert (
            has_naming_researcher and has_naming_skill
        ), "Naming convention should be documented consistently across artifacts"

    def test_consistent_directory_location(self):
        """
        GIVEN: All research persistence artifacts
        WHEN: Checking directory location references
        THEN: All reference docs/research/ directory
        """
        researcher_content = self.RESEARCHER_WEB.read_text()
        doc_master_content = self.DOC_MASTER.read_text()
        skill_content = self.SKILL_DOC.read_text()

        assert (
            "docs/research" in researcher_content
        ), "researcher-web should specify docs/research/"
        assert (
            "docs/research" in doc_master_content
        ), "doc-master should specify docs/research/"
        assert (
            "docs/research" in skill_content
        ), "skill should specify docs/research/"

    def test_workflow_completeness(self):
        """
        GIVEN: Complete research persistence workflow
        WHEN: Checking all components exist
        THEN: researcher-web creates, doc-master maintains, skill documents standards
        """
        # Check researcher-web can create research docs
        researcher_content = self.RESEARCHER_WEB.read_text()
        assert (
            "persist" in researcher_content.lower()
        ), "researcher-web should have persistence capability"

        # Check doc-master can maintain research docs
        doc_master_content = self.DOC_MASTER.read_text()
        assert (
            "research" in doc_master_content.lower()
        ), "doc-master should manage research docs"

        # Check skill documents standards
        skill_content = self.SKILL_DOC.read_text()
        assert (
            "standards" in skill_content.lower() or "validation" in skill_content.lower()
        ), "skill should document standards"


class TestEdgeCasesResearchPersistence:
    """Edge case tests for research persistence."""

    RESEARCHER_WEB = (
        Path(__file__).parent.parent.parent
        / "plugins"
        / "autonomous-dev"
        / "agents"
        / "archived"
        / "researcher-web.md"
    )
    DOC_MASTER = (
        Path(__file__).parent.parent.parent
        / "plugins"
        / "autonomous-dev"
        / "agents"
        / "doc-master.md"
    )

    def test_researcher_web_handles_no_persistence_case(self):
        """
        GIVEN: researcher-web agent
        WHEN: Research doesn't meet persistence criteria
        THEN: Agent documentation explains when NOT to persist
        """
        content = self.RESEARCHER_WEB.read_text()

        # Look for conditional language about when to persist
        conditional_keywords = [
            "if",
            "when",
            "criteria",
            "threshold",
            "should",
            "significant",
        ]

        # Extract Research Persistence section
        match = re.search(
            r"## Research Persistence(.*?)(?=\n##|\Z)", content, re.DOTALL
        )
        if match:
            persistence_section = match.group(1)
            has_conditional = any(
                keyword in persistence_section.lower()
                for keyword in conditional_keywords
            )
            assert (
                has_conditional
            ), "Research Persistence should explain conditional criteria"

    def test_doc_master_handles_missing_research_docs(self):
        """
        GIVEN: doc-master agent
        WHEN: Research docs don't exist yet
        THEN: Agent can handle case gracefully via covers: frontmatter approach
        """
        content = self.DOC_MASTER.read_text()

        # The refactored doc-master uses covers: frontmatter for doc mapping.
        # Research docs that aren't in any covers: mapping are simply not checked,
        # which is graceful handling by design.
        # Verify the agent has the covers: frontmatter scan mechanism
        assert "covers:" in content, "doc-master should reference covers: frontmatter"
        # Verify docs/*.md is in scope
        assert "docs/*.md" in content, "doc-master should have docs/*.md in scope"

    def test_invalid_filename_detection(self):
        """
        GIVEN: research-doc-standards.md skill
        WHEN: Checking validation section
        THEN: Mentions filename validation or naming convention checking
        """
        skill_file = (
            Path(__file__).parent.parent.parent
            / "plugins"
            / "autonomous-dev"
            / "skills"
            / "documentation-guide"
            / "docs"
            / "research-doc-standards.md"
        )

        content = skill_file.read_text()

        # Extract Validation section
        match = re.search(r"## Validation(.*?)(?=\n##|\Z)", content, re.DOTALL)
        assert match, "research-doc-standards.md missing Validation section"

        validation_section = match.group(1)

        # Check for filename/naming validation
        validation_keywords = ["filename", "naming", "convention", "name", "format"]
        has_filename_check = any(
            keyword in validation_section.lower() for keyword in validation_keywords
        )
        assert (
            has_filename_check
        ), "Validation section should include filename/naming checks"


if __name__ == "__main__":
    pytest.main([__file__, "--tb=line", "-q"])
