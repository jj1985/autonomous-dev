#!/usr/bin/env python3
"""
Regression Tests for Proactive Template Reload in Batch Mode (Issue #851)

Verifies the proactive reload contract:
1. All critical agents have readable templates.
2. Each get_agent_prompt_template() call reads fresh from disk (no caching).
3. Missing agent templates raise FileNotFoundError.
4. Word counts from get_agent_prompt_template() match compute_template_baselines().
5-8. Acceptance tests: implement-batch.md contains the required protocol text.
"""

import sys
from pathlib import Path

import pytest

# Portable project root detection — works from any CWD
_current = Path(__file__).resolve()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        PROJECT_ROOT = _current
        break
    _current = _current.parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[4]  # fallback

sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "autonomous-dev" / "lib"))

from prompt_integrity import (
    COMPRESSION_CRITICAL_AGENTS,
    compute_template_baselines,
    get_agent_prompt_template,
)


class TestAllCriticalAgentsHaveTemplates:
    """Test that every agent in COMPRESSION_CRITICAL_AGENTS has a readable template."""

    def test_all_critical_agents_have_templates(self, tmp_path: Path) -> None:
        """Iterate COMPRESSION_CRITICAL_AGENTS; each must return non-empty string."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        # Create stub template files for all critical agents
        for agent in COMPRESSION_CRITICAL_AGENTS:
            agent_file = agents_dir / f"{agent}.md"
            agent_file.write_text(
                f"# {agent.title()} Agent\n\n"
                "You are a specialist agent. Your role is to perform thorough analysis. "
                "This template has enough words to exceed the minimum threshold. " * 5
            )

        for agent in sorted(COMPRESSION_CRITICAL_AGENTS):
            template = get_agent_prompt_template(agent, agents_dir=agents_dir)
            assert isinstance(template, str), (
                f"get_agent_prompt_template('{agent}') must return a str"
            )
            assert len(template) > 0, (
                f"get_agent_prompt_template('{agent}') must return non-empty string"
            )

    def test_compression_critical_agents_is_non_empty_set(self) -> None:
        """COMPRESSION_CRITICAL_AGENTS must be a non-empty set."""
        assert isinstance(COMPRESSION_CRITICAL_AGENTS, (set, frozenset))
        assert len(COMPRESSION_CRITICAL_AGENTS) > 0


class TestProactiveReloadReturnsDiskContentNotCached:
    """Test that get_agent_prompt_template() always reads fresh from disk."""

    def test_proactive_reload_returns_disk_content_not_cached(
        self, tmp_path: Path
    ) -> None:
        """Write a temp agent file, read it, modify it on disk, re-read — verify updated content."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        agent_file = agents_dir / "reviewer.md"

        # First write
        original_content = "# Reviewer\n\nOriginal content for reviewer agent.\n"
        agent_file.write_text(original_content)
        result1 = get_agent_prompt_template("reviewer", agents_dir=agents_dir)
        assert result1 == original_content, "First read should return original content"

        # Modify on disk (simulates template update between issues)
        updated_content = "# Reviewer\n\nUpdated content after disk modification.\n"
        agent_file.write_text(updated_content)
        result2 = get_agent_prompt_template("reviewer", agents_dir=agents_dir)

        # Must return updated content — no caching
        assert result2 == updated_content, (
            "Second read must return updated disk content — "
            "get_agent_prompt_template() must NOT cache between calls"
        )
        assert result1 != result2, (
            "Two reads with different disk content must return different results"
        )

    def test_reload_reads_correct_agent_file(self, tmp_path: Path) -> None:
        """Each agent type reads its own file, not another agent's file."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        for agent in ["reviewer", "implementer", "planner"]:
            (agents_dir / f"{agent}.md").write_text(f"Content for {agent}\n")

        for agent in ["reviewer", "implementer", "planner"]:
            template = get_agent_prompt_template(agent, agents_dir=agents_dir)
            assert f"Content for {agent}" in template, (
                f"Template for '{agent}' must contain that agent's content"
            )


class TestProactiveReloadSkipsMissingAgent:
    """Test behavior when the agent template file does not exist."""

    def test_proactive_reload_skips_missing_agent(self, tmp_path: Path) -> None:
        """Call get_agent_prompt_template for a nonexistent agent — must raise FileNotFoundError."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        # Do NOT create any agent files

        with pytest.raises(FileNotFoundError) as exc_info:
            get_agent_prompt_template("nonexistent-agent", agents_dir=agents_dir)

        error_msg = str(exc_info.value)
        assert "nonexistent-agent" in error_msg, (
            "FileNotFoundError message must mention the missing agent name"
        )

    def test_proactive_reload_missing_raises_not_returns_none(
        self, tmp_path: Path
    ) -> None:
        """Missing agent template must raise, not silently return None or empty string."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        with pytest.raises(FileNotFoundError):
            get_agent_prompt_template("ghost-agent", agents_dir=agents_dir)


class TestWordCountsMatchComputeBaselines:
    """Test that word counts from get_agent_prompt_template match compute_template_baselines."""

    def test_word_counts_match_compute_baselines(self, tmp_path: Path) -> None:
        """Word count of each template must match compute_template_baselines() output."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        test_agents = ["reviewer", "implementer", "planner"]
        expected_word_counts = {}

        for agent in test_agents:
            content = (
                f"# {agent.title()} Agent\n\n"
                f"You are the {agent} specialist. "
                "Perform thorough work on every task. "
                "Quality is paramount. " * 3
            )
            (agents_dir / f"{agent}.md").write_text(content)
            expected_word_counts[agent] = len(content.split())

        baselines = compute_template_baselines(agents_dir=agents_dir)

        for agent in test_agents:
            assert agent in baselines, (
                f"compute_template_baselines() must include '{agent}'"
            )
            template = get_agent_prompt_template(agent, agents_dir=agents_dir)
            direct_word_count = len(template.split())
            baseline_word_count = baselines[agent]
            assert direct_word_count == baseline_word_count, (
                f"Word count for '{agent}' must match between "
                f"get_agent_prompt_template() ({direct_word_count}) and "
                f"compute_template_baselines() ({baseline_word_count})"
            )


# ---------------------------------------------------------------------------
# Acceptance tests — verify implement-batch.md contains the required protocol
# ---------------------------------------------------------------------------

BATCH_CMD_PATH = (
    PROJECT_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement-batch.md"
)


@pytest.fixture(scope="module")
def batch_cmd_text() -> str:
    """Read implement-batch.md once for all acceptance tests."""
    assert BATCH_CMD_PATH.exists(), (
        f"implement-batch.md not found at {BATCH_CMD_PATH}"
    )
    return BATCH_CMD_PATH.read_text(encoding="utf-8")


class TestAC1ProtocolStepExistsInBatchCmd:
    """AC1: implement-batch.md references the proactive reload protocol."""

    def test_ac1_references_get_agent_prompt_template(self, batch_cmd_text: str) -> None:
        """implement-batch.md must reference get_agent_prompt_template."""
        assert "get_agent_prompt_template" in batch_cmd_text, (
            "implement-batch.md must reference get_agent_prompt_template "
            "in the proactive reload protocol (Issue #851)"
        )

    def test_ac1_references_compression_critical_agents(self, batch_cmd_text: str) -> None:
        """implement-batch.md must reference COMPRESSION_CRITICAL_AGENTS."""
        assert "COMPRESSION_CRITICAL_AGENTS" in batch_cmd_text, (
            "implement-batch.md must reference COMPRESSION_CRITICAL_AGENTS "
            "in the proactive reload protocol (Issue #851)"
        )

    def test_ac1_marked_as_hard_gate(self, batch_cmd_text: str) -> None:
        """The proactive reload step must be marked HARD GATE."""
        assert "HARD GATE" in batch_cmd_text, (
            "implement-batch.md must contain a HARD GATE marker"
        )

    def test_ac1_contains_proactive_reload_header(self, batch_cmd_text: str) -> None:
        """The section must be titled 'Proactive Template Reload'."""
        assert "Proactive Template Reload" in batch_cmd_text, (
            "implement-batch.md must contain 'Proactive Template Reload' section header (Issue #851)"
        )


class TestAC2RunnableCodeSnippet:
    """AC2: implement-batch.md contains the runnable Python snippet."""

    def test_ac2_python_snippet_present(self, batch_cmd_text: str) -> None:
        """The Python snippet calling get_agent_prompt_template must be present."""
        assert "python3 -c" in batch_cmd_text, (
            "implement-batch.md must contain a python3 -c inline snippet "
            "for the proactive reload (Issue #851)"
        )

    def test_ac2_snippet_calls_get_agent_prompt_template_per_agent(
        self, batch_cmd_text: str
    ) -> None:
        """The snippet must call get_agent_prompt_template in a loop over agents."""
        assert "get_agent_prompt_template(agent)" in batch_cmd_text, (
            "The proactive reload snippet must call get_agent_prompt_template(agent) "
            "in a loop over COMPRESSION_CRITICAL_AGENTS (Issue #851)"
        )

    def test_ac2_snippet_includes_fresh_from_disk_output(
        self, batch_cmd_text: str
    ) -> None:
        """The snippet output message must include 'fresh from disk'."""
        assert "fresh from disk" in batch_cmd_text, (
            "The proactive reload snippet must print '... (fresh from disk)' "
            "to confirm disk reads (Issue #851)"
        )


class TestAC3CrossReferenceInPromptIntegritySection:
    """AC3: The 'Prompt Integrity Across Issues' section references Issue #851."""

    def test_ac3_prompt_integrity_section_references_issue_851(
        self, batch_cmd_text: str
    ) -> None:
        """The Prompt Integrity section must cross-reference Issue #851."""
        # Find the Prompt Integrity section
        section_marker = "HARD GATE: Prompt Integrity Across Issues"
        assert section_marker in batch_cmd_text, (
            f"implement-batch.md must contain the '{section_marker}' section"
        )

        # Find Issue #851 reference within the file
        assert "Issue #851" in batch_cmd_text, (
            "implement-batch.md must reference Issue #851 "
            "in the Prompt Integrity section (cross-reference to proactive reload)"
        )

    def test_ac3_proactive_prevention_note_present(self, batch_cmd_text: str) -> None:
        """The cross-reference note must say 'Proactive Prevention (Issue #851)'."""
        assert "Proactive Prevention (Issue #851)" in batch_cmd_text, (
            "implement-batch.md must contain 'Proactive Prevention (Issue #851)' "
            "as a cross-reference note in the Prompt Integrity section"
        )


class TestAC4NoNewFunctionsInPromptIntegrity:
    """AC4: prompt_integrity.py must NOT add a new reload_all_agent_templates function."""

    def test_ac4_no_reload_all_agent_templates_function(self) -> None:
        """prompt_integrity.py must NOT define reload_all_agent_templates()."""
        prompt_integrity_path = (
            PROJECT_ROOT
            / "plugins"
            / "autonomous-dev"
            / "lib"
            / "prompt_integrity.py"
        )
        assert prompt_integrity_path.exists(), (
            f"prompt_integrity.py not found at {prompt_integrity_path}"
        )
        source = prompt_integrity_path.read_text(encoding="utf-8")
        assert "def reload_all_agent_templates" not in source, (
            "prompt_integrity.py must NOT define reload_all_agent_templates() — "
            "the implementation reuses existing get_agent_prompt_template() (Issue #851)"
        )

    def test_ac4_existing_get_agent_prompt_template_function_exists(self) -> None:
        """get_agent_prompt_template() must exist (the function being reused)."""
        prompt_integrity_path = (
            PROJECT_ROOT
            / "plugins"
            / "autonomous-dev"
            / "lib"
            / "prompt_integrity.py"
        )
        source = prompt_integrity_path.read_text(encoding="utf-8")
        assert "def get_agent_prompt_template" in source, (
            "prompt_integrity.py must define get_agent_prompt_template() "
            "which is the function reused by the proactive reload protocol"
        )
