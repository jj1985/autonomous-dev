"""Spec validation tests for Issue #839: Agent verification language upgrade.

Validates acceptance criteria:
1. Zero casual "check for/if/whether/that" in active agents
2. reviewer.md has 5+ named review dimensions
3. researcher.md uses cross-referencing language
4. implementer.md uses decomposition language
5. doc-master.md uses classification language
6. test-master.md has ordering dependency language
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKTREE = Path(__file__).resolve().parents[2]
AGENTS_DIR = WORKTREE / "plugins" / "autonomous-dev" / "agents"

ACTIVE_AGENT_FILES = [
    "security-auditor.md",
    "reviewer.md",
    "continuous-improvement-analyst.md",
    "test-master.md",
    "ui-tester.md",
    "planner.md",
    "researcher.md",
    "implementer.md",
    "doc-master.md",
]


@pytest.fixture
def agent_contents() -> dict[str, str]:
    """Load contents of all active agent files."""
    contents = {}
    for name in ACTIVE_AGENT_FILES:
        path = AGENTS_DIR / name
        assert path.exists(), f"Agent file not found: {path}"
        contents[name] = path.read_text()
    return contents


CASUAL_CHECK_PATTERN = re.compile(
    r"\bcheck\s+(for|if|whether|that)\b", re.IGNORECASE
)


def _strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks and inline code from markdown."""
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    return text


class TestSpec839:

    def test_spec_839_1_zero_casual_check_in_active_agents(self, agent_contents):
        """No active agent file contains casual check for/if/whether/that in prose."""
        violations = []
        for name, content in agent_contents.items():
            prose = _strip_code_blocks(content)
            for i, line in enumerate(prose.splitlines(), 1):
                if CASUAL_CHECK_PATTERN.search(line):
                    violations.append(f"{name}:{i}: {line.strip()}")

        assert not violations, (
            f"Found casual check for/if/whether/that in active agents:\n"
            + "\n".join(violations)
        )

    def test_spec_839_2_reviewer_has_5_plus_named_dimensions(self, agent_contents):
        """reviewer.md must have at least 5 distinctly named review dimensions."""
        content = agent_contents["reviewer.md"]
        dimensions_section = re.search(
            r"## Review Dimensions\s*\n(.*?)(?=\n##|\Z)",
            content,
            re.DOTALL,
        )
        assert dimensions_section is not None, (
            "reviewer.md missing Review Dimensions section"
        )
        dimension_names = re.findall(
            r"^\d+\.\s+\*\*([\w][\w\s]*?)\*\*",
            dimensions_section.group(1),
            re.MULTILINE,
        )
        assert len(dimension_names) >= 5, (
            f"reviewer.md has only {len(dimension_names)} named review dimensions "
            f"(need 5+): {dimension_names}"
        )

    def test_spec_839_3_researcher_uses_cross_referencing(self, agent_contents):
        """researcher.md must contain cross-referencing language."""
        content = agent_contents["researcher.md"]
        assert re.search(r"cross-referenc", content, re.IGNORECASE), (
            "researcher.md does not contain cross-reference or cross-referencing"
        )

    def test_spec_839_4_implementer_uses_decomposition(self, agent_contents):
        """implementer.md must contain decomposition language."""
        content = agent_contents["implementer.md"]
        assert re.search(r"\bdecompos", content, re.IGNORECASE), (
            "implementer.md does not contain decompose or decomposition"
        )

    def test_spec_839_5_doc_master_uses_classification(self, agent_contents):
        """doc-master.md must contain classification language."""
        content = agent_contents["doc-master.md"]
        assert re.search(r"\bclassif", content, re.IGNORECASE), (
            "doc-master.md does not contain classify or classification"
        )

    def test_spec_839_6_test_master_has_ordering_dependency(self, agent_contents):
        """test-master.md must contain ordering/dependency language in workflow."""
        content = agent_contents["test-master.md"]
        has_ordering = re.search(r"\border(ing)?\b", content, re.IGNORECASE)
        has_dependency = re.search(r"\bdepend(s|ency|encies|ent)?\b", content, re.IGNORECASE)
        assert has_ordering or has_dependency, (
            "test-master.md does not contain ordering or dependency language"
        )
