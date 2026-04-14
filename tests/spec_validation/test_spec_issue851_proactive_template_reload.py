#!/usr/bin/env python3
"""
Spec validation tests for Issue #851: Proactive prompt template reload in batch mode.

Tests observable behavior against the acceptance criteria ONLY.
"""

import sys
from pathlib import Path

import pytest

# Portable project root detection
_current = Path(__file__).resolve()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        PROJECT_ROOT = _current
        break
    _current = _current.parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "autonomous-dev" / "lib"))

from prompt_integrity import (
    COMPRESSION_CRITICAL_AGENTS,
    compute_template_baselines,
    get_agent_prompt_template,
)

BATCH_CMD_PATH = (
    PROJECT_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement-batch.md"
)


@pytest.fixture(scope="module")
def batch_cmd_text() -> str:
    """Read implement-batch.md once for all tests."""
    assert BATCH_CMD_PATH.exists(), f"implement-batch.md not found at {BATCH_CMD_PATH}"
    return BATCH_CMD_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AC1: implement-batch.md contains a REQUIRED protocol step that instructs
# the coordinator to call get_agent_prompt_template() for all critical agents
# at the start of each issue pipeline, before any agent dispatch.
# ---------------------------------------------------------------------------


class TestSpec851AC1ProtocolStep:
    """AC1: Proactive reload protocol step exists in implement-batch.md."""

    def test_spec_851_1_references_get_agent_prompt_template(
        self, batch_cmd_text: str
    ) -> None:
        """implement-batch.md must mention get_agent_prompt_template."""
        assert "get_agent_prompt_template" in batch_cmd_text

    def test_spec_851_2_references_compression_critical_agents(
        self, batch_cmd_text: str
    ) -> None:
        """implement-batch.md must mention COMPRESSION_CRITICAL_AGENTS."""
        assert "COMPRESSION_CRITICAL_AGENTS" in batch_cmd_text

    def test_spec_851_3_has_proactive_reload_section(
        self, batch_cmd_text: str
    ) -> None:
        """implement-batch.md must contain a Proactive Template Reload section."""
        assert "Proactive Template Reload" in batch_cmd_text


# ---------------------------------------------------------------------------
# AC2: The protocol step includes a runnable code snippet that reads
# templates from disk and logs word counts.
# ---------------------------------------------------------------------------


class TestSpec851AC2RunnableSnippet:
    """AC2: Runnable code snippet for template reload with word counts."""

    def test_spec_851_4_contains_runnable_snippet(
        self, batch_cmd_text: str
    ) -> None:
        """implement-batch.md must contain a Python snippet calling the function."""
        assert "get_agent_prompt_template(agent" in batch_cmd_text

    def test_spec_851_5_snippet_logs_word_counts(
        self, batch_cmd_text: str
    ) -> None:
        """The snippet must log word counts."""
        text_lower = batch_cmd_text.lower()
        assert "word" in text_lower and "count" in text_lower


# ---------------------------------------------------------------------------
# AC3: The existing HARD GATE Prompt Integrity Across Issues section
# cross-references the proactive reload (Issue #851).
# ---------------------------------------------------------------------------


class TestSpec851AC3CrossReference:
    """AC3: Prompt Integrity section cross-references Issue #851."""

    def test_spec_851_6_prompt_integrity_section_exists(
        self, batch_cmd_text: str
    ) -> None:
        """implement-batch.md must contain the Prompt Integrity HARD GATE section."""
        assert "Prompt Integrity Across Issues" in batch_cmd_text

    def test_spec_851_7_cross_references_issue_851(
        self, batch_cmd_text: str
    ) -> None:
        """The Prompt Integrity section must reference Issue #851."""
        assert "Issue #851" in batch_cmd_text or "#851" in batch_cmd_text


# ---------------------------------------------------------------------------
# AC4: No new functions are added to prompt_integrity.py -- the plan reuses
# get_agent_prompt_template and COMPRESSION_CRITICAL_AGENTS directly.
# ---------------------------------------------------------------------------


class TestSpec851AC4NoNewFunctions:
    """AC4: prompt_integrity.py does not add new convenience functions."""

    def test_spec_851_8_no_reload_all_function(self) -> None:
        """prompt_integrity.py must NOT define a new reload_all_agent_templates function."""
        source = (
            PROJECT_ROOT
            / "plugins"
            / "autonomous-dev"
            / "lib"
            / "prompt_integrity.py"
        ).read_text(encoding="utf-8")
        assert "def reload_all_agent_templates" not in source

    def test_spec_851_9_existing_api_preserved(self) -> None:
        """get_agent_prompt_template and COMPRESSION_CRITICAL_AGENTS must exist."""
        assert callable(get_agent_prompt_template)
        assert isinstance(COMPRESSION_CRITICAL_AGENTS, (set, frozenset))
        assert len(COMPRESSION_CRITICAL_AGENTS) > 0


# ---------------------------------------------------------------------------
# AC5: Regression tests verify get_agent_prompt_template returns fresh-from-disk
# content (no caching), handles missing agents, word counts match baselines.
# ---------------------------------------------------------------------------


class TestSpec851AC5FreshFromDisk:
    """AC5a: get_agent_prompt_template returns fresh content on every call."""

    def test_spec_851_10_no_caching(self, tmp_path: Path) -> None:
        """Modifying a template file on disk must be reflected on next read."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        agent_file = agents_dir / "reviewer.md"

        agent_file.write_text("# Reviewer\n\nOriginal content version one.\n")
        result1 = get_agent_prompt_template("reviewer", agents_dir=agents_dir)

        agent_file.write_text("# Reviewer\n\nUpdated content version two.\n")
        result2 = get_agent_prompt_template("reviewer", agents_dir=agents_dir)

        assert "version one" in result1
        assert "version two" in result2
        assert result1 != result2


class TestSpec851AC5MissingAgent:
    """AC5b: Missing agent templates are handled correctly."""

    def test_spec_851_11_missing_agent_raises(self, tmp_path: Path) -> None:
        """Requesting a nonexistent agent template must raise FileNotFoundError."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        with pytest.raises(FileNotFoundError):
            get_agent_prompt_template("nonexistent-agent", agents_dir=agents_dir)


class TestSpec851AC5WordCountMatch:
    """AC5c: Word counts from get_agent_prompt_template match compute_template_baselines."""

    def test_spec_851_12_word_counts_consistent(self, tmp_path: Path) -> None:
        """Word count via direct template read must equal compute_template_baselines output."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        test_content = {
            "reviewer": "You are a code reviewer specialist agent with deep expertise.",
            "implementer": "You are the implementer agent responsible for writing code.",
            "planner": "You are the planner agent responsible for creating plans.",
        }

        for agent, content in test_content.items():
            (agents_dir / f"{agent}.md").write_text(content)

        baselines = compute_template_baselines(agents_dir=agents_dir)

        for agent, content in test_content.items():
            if agent in baselines:
                template = get_agent_prompt_template(agent, agents_dir=agents_dir)
                direct_count = len(template.split())
                assert direct_count == baselines[agent], (
                    f"Word count mismatch for {agent}: "
                    f"direct={direct_count}, baseline={baselines[agent]}"
                )


# ---------------------------------------------------------------------------
# AC6: All existing tests continue to pass (verified by running this file
# alongside the existing test suite -- not a standalone test).
# ---------------------------------------------------------------------------


class TestSpec851AC6ExistingTestsLocation:
    """AC6: The implementer regression tests exist at the specified path."""

    def test_spec_851_13_regression_test_file_exists(self) -> None:
        """tests/unit/lib/test_prompt_integrity_proactive.py must exist."""
        test_path = (
            PROJECT_ROOT / "tests" / "unit" / "lib" / "test_prompt_integrity_proactive.py"
        )
        assert test_path.exists(), (
            f"Regression test file not found at {test_path}"
        )
