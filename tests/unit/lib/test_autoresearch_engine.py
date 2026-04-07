"""Tests for autoresearch_engine.py — autonomous experiment loop mechanics.

GitHub Issue: #654
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add lib to path
_LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(_LIB_DIR))

from autoresearch_engine import (
    ALLOWED_TARGET_PATTERNS,
    ExperimentConfig,
    ExperimentHistory,
    check_stall,
    commit_improvement,
    create_experiment_branch,
    revert_target,
    run_metric,
    validate_metric,
    validate_target,
)


# ---------------------------------------------------------------------------
# Target validation
# ---------------------------------------------------------------------------


class TestValidateTarget:
    """Tests for validate_target whitelist enforcement."""

    def test_valid_agent_target(self, tmp_path: Path) -> None:
        """Agent .md files should be accepted."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        target = agents_dir / "researcher.md"
        target.write_text("# Researcher")

        valid, err = validate_target(target, repo_root=tmp_path)
        assert valid is True
        assert err == ""

    def test_valid_skill_target(self, tmp_path: Path) -> None:
        """Skill SKILL.md files should be accepted."""
        skill_dir = tmp_path / "skills" / "python-standards"
        skill_dir.mkdir(parents=True)
        target = skill_dir / "SKILL.md"
        target.write_text("# Skill")

        valid, err = validate_target(target, repo_root=tmp_path)
        assert valid is True
        assert err == ""

    def test_reject_arbitrary_file(self, tmp_path: Path) -> None:
        """Non-whitelisted files should be rejected."""
        target = tmp_path / "README.md"
        target.write_text("# Readme")

        valid, err = validate_target(target, repo_root=tmp_path)
        assert valid is False
        assert "does not match allowed patterns" in err

    def test_reject_lib_file(self, tmp_path: Path) -> None:
        """lib/*.py files should be rejected."""
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        target = lib_dir / "engine.py"
        target.write_text("pass")

        valid, err = validate_target(target, repo_root=tmp_path)
        assert valid is False
        assert "does not match" in err

    def test_reject_path_traversal(self, tmp_path: Path) -> None:
        """Path traversal attempts should be rejected."""
        # Create a file outside repo_root
        outside = tmp_path.parent / "outside.md"
        outside.write_text("exploit")

        valid, err = validate_target(outside, repo_root=tmp_path)
        assert valid is False
        assert "outside repository root" in err

    def test_reject_nonexistent_target(self, tmp_path: Path) -> None:
        """Target file must exist."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        target = agents_dir / "ghost.md"

        valid, err = validate_target(target, repo_root=tmp_path)
        assert valid is False
        assert "does not exist" in err

    def test_reject_deeply_nested_agent(self, tmp_path: Path) -> None:
        """agents/sub/deep.md should NOT match agents/*.md."""
        deep_dir = tmp_path / "agents" / "sub"
        deep_dir.mkdir(parents=True)
        target = deep_dir / "deep.md"
        target.write_text("# Deep")

        valid, err = validate_target(target, repo_root=tmp_path)
        assert valid is False


# ---------------------------------------------------------------------------
# Metric validation
# ---------------------------------------------------------------------------


class TestValidateMetric:
    """Tests for validate_metric file checks."""

    def test_valid_metric_script(self, tmp_path: Path) -> None:
        """Existing file should pass."""
        script = tmp_path / "benchmark.py"
        script.write_text("print('METRIC: 0.85')")

        valid, err = validate_metric(script)
        assert valid is True
        assert err == ""

    def test_missing_metric_script(self, tmp_path: Path) -> None:
        """Non-existent script should fail."""
        script = tmp_path / "nonexistent.py"

        valid, err = validate_metric(script)
        assert valid is False
        assert "not found" in err

    def test_metric_script_is_directory(self, tmp_path: Path) -> None:
        """Directory should fail."""
        valid, err = validate_metric(tmp_path)
        assert valid is False
        assert "not a file" in err


# ---------------------------------------------------------------------------
# Metric output parsing
# ---------------------------------------------------------------------------


class TestRunMetric:
    """Tests for run_metric script execution and output parsing."""

    @patch("autoresearch_engine.subprocess.run")
    def test_parse_valid_metric(self, mock_run: MagicMock) -> None:
        """Should parse METRIC: <float> from stdout."""
        mock_run.return_value = MagicMock(
            stdout="Starting benchmark...\nMETRIC: 0.856\nDone.\n",
            stderr="",
        )

        value, output = run_metric(Path("bench.py"))
        assert value == pytest.approx(0.856)

    @patch("autoresearch_engine.subprocess.run")
    def test_parse_metric_from_stderr(self, mock_run: MagicMock) -> None:
        """Should also find METRIC line in stderr."""
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="METRIC: 0.923\n",
        )

        value, output = run_metric(Path("bench.py"))
        assert value == pytest.approx(0.923)

    @patch("autoresearch_engine.subprocess.run")
    def test_missing_metric_line(self, mock_run: MagicMock) -> None:
        """Should raise ValueError if no METRIC line found."""
        mock_run.return_value = MagicMock(
            stdout="No metric here\n",
            stderr="",
        )

        with pytest.raises(ValueError, match="No 'METRIC: <float>' line found"):
            run_metric(Path("bench.py"))

    @patch("autoresearch_engine.subprocess.run")
    def test_last_metric_line_used(self, mock_run: MagicMock) -> None:
        """When multiple METRIC lines exist, use the last one."""
        mock_run.return_value = MagicMock(
            stdout="METRIC: 0.5\nMETRIC: 0.9\n",
            stderr="",
        )

        value, output = run_metric(Path("bench.py"))
        assert value == pytest.approx(0.9)

    @patch("autoresearch_engine.subprocess.run")
    def test_scientific_notation_metric(self, mock_run: MagicMock) -> None:
        """Should parse scientific notation."""
        mock_run.return_value = MagicMock(
            stdout="METRIC: 1.5e-3\n",
            stderr="",
        )

        value, output = run_metric(Path("bench.py"))
        assert value == pytest.approx(0.0015)

    @patch("autoresearch_engine.subprocess.run")
    def test_negative_metric(self, mock_run: MagicMock) -> None:
        """Should parse negative values."""
        mock_run.return_value = MagicMock(
            stdout="METRIC: -0.42\n",
            stderr="",
        )

        value, output = run_metric(Path("bench.py"))
        assert value == pytest.approx(-0.42)


# ---------------------------------------------------------------------------
# ExperimentHistory
# ---------------------------------------------------------------------------


class TestExperimentHistory:
    """Tests for JSONL experiment history tracking."""

    def test_append_and_load(self, tmp_path: Path) -> None:
        """Append an entry and load it back."""
        history = ExperimentHistory(tmp_path / "history.jsonl")
        history.append(
            hypothesis="Add structured output section",
            metric_before=0.80,
            metric_after=0.85,
            outcome="improved",
        )

        entries = history.load_all()
        assert len(entries) == 1
        assert entries[0]["hypothesis"] == "Add structured output section"
        assert entries[0]["metric_before"] == 0.80
        assert entries[0]["metric_after"] == 0.85
        assert entries[0]["outcome"] == "improved"
        assert entries[0]["delta"] == pytest.approx(0.05)

    def test_load_empty_file(self, tmp_path: Path) -> None:
        """Loading a non-existent file returns empty list."""
        history = ExperimentHistory(tmp_path / "does_not_exist.jsonl")
        assert history.load_all() == []

    def test_load_recent(self, tmp_path: Path) -> None:
        """load_recent returns newest first."""
        history = ExperimentHistory(tmp_path / "history.jsonl")
        for i in range(5):
            history.append(
                hypothesis=f"Hypothesis {i}",
                metric_before=float(i),
                metric_after=float(i + 1),
                outcome="improved",
            )

        recent = history.load_recent(3)
        assert len(recent) == 3
        assert recent[0]["hypothesis"] == "Hypothesis 4"  # newest first
        assert recent[2]["hypothesis"] == "Hypothesis 2"

    def test_corrupt_line_tolerance(self, tmp_path: Path) -> None:
        """Corrupt lines should be skipped without crashing."""
        history_file = tmp_path / "history.jsonl"
        history_file.write_text(
            '{"hypothesis": "good", "outcome": "improved"}\n'
            "THIS IS NOT JSON\n"
            '{"hypothesis": "also good", "outcome": "reverted"}\n'
        )

        history = ExperimentHistory(history_file)
        entries = history.load_all()
        assert len(entries) == 2

    def test_consecutive_failures_none(self, tmp_path: Path) -> None:
        """Zero consecutive failures when last entry is improved."""
        history = ExperimentHistory(tmp_path / "history.jsonl")
        history.append(
            hypothesis="H1",
            metric_before=0.8,
            metric_after=0.85,
            outcome="improved",
        )

        assert history.consecutive_failures() == 0

    def test_consecutive_failures_all(self, tmp_path: Path) -> None:
        """All entries are failures."""
        history = ExperimentHistory(tmp_path / "history.jsonl")
        for i in range(4):
            history.append(
                hypothesis=f"H{i}",
                metric_before=0.8,
                metric_after=0.79,
                outcome="reverted",
            )

        assert history.consecutive_failures() == 4

    def test_consecutive_failures_reset_by_success(self, tmp_path: Path) -> None:
        """Success resets the consecutive failure counter."""
        history = ExperimentHistory(tmp_path / "history.jsonl")
        # 2 failures, 1 success, 1 failure
        history.append(hypothesis="H0", metric_before=0.8, metric_after=0.79, outcome="reverted")
        history.append(hypothesis="H1", metric_before=0.8, metric_after=0.79, outcome="reverted")
        history.append(hypothesis="H2", metric_before=0.8, metric_after=0.85, outcome="improved")
        history.append(hypothesis="H3", metric_before=0.85, metric_after=0.84, outcome="reverted")

        assert history.consecutive_failures() == 1

    def test_consecutive_failures_empty(self, tmp_path: Path) -> None:
        """Empty history has zero consecutive failures."""
        history = ExperimentHistory(tmp_path / "empty.jsonl")
        assert history.consecutive_failures() == 0

    def test_summary(self, tmp_path: Path) -> None:
        """Summary should aggregate outcomes."""
        history = ExperimentHistory(tmp_path / "history.jsonl")
        history.append(hypothesis="H1", metric_before=0.8, metric_after=0.85, outcome="improved")
        history.append(hypothesis="H2", metric_before=0.85, metric_after=0.84, outcome="reverted")
        history.append(hypothesis="H3", metric_before=0.85, metric_after=0.90, outcome="improved")

        summary = history.summary()
        assert summary["total"] == 3
        assert summary["improved"] == 2
        assert summary["reverted"] == 1
        assert summary["error"] == 0
        assert summary["best_delta"] == pytest.approx(0.05)
        assert summary["worst_delta"] == pytest.approx(-0.01)

    def test_summary_empty(self, tmp_path: Path) -> None:
        """Summary of empty history returns zeros."""
        history = ExperimentHistory(tmp_path / "empty.jsonl")
        summary = history.summary()
        assert summary["total"] == 0
        assert summary["best_delta"] == 0.0

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Append should create parent directories."""
        deep_path = tmp_path / "a" / "b" / "c" / "history.jsonl"
        history = ExperimentHistory(deep_path)
        history.append(hypothesis="H1", metric_before=0.8, metric_after=0.85, outcome="improved")

        assert deep_path.exists()
        assert len(history.load_all()) == 1


# ---------------------------------------------------------------------------
# Stall detection
# ---------------------------------------------------------------------------


class TestCheckStall:
    """Tests for stall detection."""

    def test_no_stall_zero_failures(self, tmp_path: Path) -> None:
        """No failures = not stalled."""
        history = ExperimentHistory(tmp_path / "h.jsonl")
        history.append(hypothesis="H1", metric_before=0.8, metric_after=0.85, outcome="improved")

        assert check_stall(history, max_consecutive=3) is False

    def test_no_stall_below_threshold(self, tmp_path: Path) -> None:
        """Failures below threshold = not stalled."""
        history = ExperimentHistory(tmp_path / "h.jsonl")
        history.append(hypothesis="H1", metric_before=0.8, metric_after=0.79, outcome="reverted")
        history.append(hypothesis="H2", metric_before=0.8, metric_after=0.79, outcome="reverted")

        assert check_stall(history, max_consecutive=3) is False

    def test_stall_at_threshold(self, tmp_path: Path) -> None:
        """Exactly N failures = stalled."""
        history = ExperimentHistory(tmp_path / "h.jsonl")
        for i in range(3):
            history.append(
                hypothesis=f"H{i}",
                metric_before=0.8,
                metric_after=0.79,
                outcome="reverted",
            )

        assert check_stall(history, max_consecutive=3) is True

    def test_stall_above_threshold(self, tmp_path: Path) -> None:
        """More than N failures = stalled."""
        history = ExperimentHistory(tmp_path / "h.jsonl")
        for i in range(5):
            history.append(
                hypothesis=f"H{i}",
                metric_before=0.8,
                metric_after=0.79,
                outcome="reverted",
            )

        assert check_stall(history, max_consecutive=3) is True

    def test_stall_reset_by_success(self, tmp_path: Path) -> None:
        """Success resets the counter, so subsequent failures may not reach threshold."""
        history = ExperimentHistory(tmp_path / "h.jsonl")
        # 2 failures, 1 success, 2 failures
        for outcome in ["reverted", "reverted", "improved", "reverted", "reverted"]:
            history.append(
                hypothesis="H",
                metric_before=0.8,
                metric_after=0.79 if outcome == "reverted" else 0.85,
                outcome=outcome,
            )

        assert check_stall(history, max_consecutive=3) is False

    def test_empty_history_not_stalled(self, tmp_path: Path) -> None:
        """Empty history should not be considered stalled."""
        history = ExperimentHistory(tmp_path / "empty.jsonl")
        assert check_stall(history, max_consecutive=3) is False


# ---------------------------------------------------------------------------
# ExperimentConfig
# ---------------------------------------------------------------------------


class TestExperimentConfig:
    """Tests for ExperimentConfig dataclass."""

    def test_default_values(self) -> None:
        """Default config values should be sensible."""
        config = ExperimentConfig(
            target=Path("agents/researcher.md"),
            metric_script=Path("bench.py"),
        )
        assert config.iterations == 20
        assert config.min_improvement == 0.01
        assert config.dry_run is False
        assert config.experiment_branch == ""
        assert config.max_stall == 3

    def test_custom_values(self) -> None:
        """Custom values should override defaults."""
        config = ExperimentConfig(
            target=Path("agents/researcher.md"),
            metric_script=Path("bench.py"),
            iterations=50,
            min_improvement=0.05,
            dry_run=True,
            max_stall=5,
        )
        assert config.iterations == 50
        assert config.min_improvement == 0.05
        assert config.dry_run is True
        assert config.max_stall == 5


# ---------------------------------------------------------------------------
# Git helpers (mocked)
# ---------------------------------------------------------------------------


class TestGitHelpers:
    """Tests for git operation wrappers."""

    @patch("autoresearch_engine.subprocess.run")
    def test_create_experiment_branch_format(self, mock_run: MagicMock) -> None:
        """Branch name should follow autoresearch/<name>-<timestamp> format."""
        mock_run.return_value = MagicMock(returncode=0)

        branch = create_experiment_branch("researcher")
        assert branch.startswith("autoresearch/researcher-")
        # Verify git checkout -b was called
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0:3] == ["git", "checkout", "-b"]

    @patch("autoresearch_engine.subprocess.run")
    def test_create_branch_sanitizes_name(self, mock_run: MagicMock) -> None:
        """Special characters in target name should be sanitized."""
        mock_run.return_value = MagicMock(returncode=0)

        branch = create_experiment_branch("skills/python standards/SKILL")
        assert "autoresearch/" in branch
        # No slashes or spaces in the sanitized name part
        name_part = branch.split("/", 1)[1]
        assert " " not in name_part

    @patch("autoresearch_engine.subprocess.run")
    def test_revert_target_calls_git(self, mock_run: MagicMock) -> None:
        """revert_target should call git checkout -- <target>."""
        mock_run.return_value = MagicMock(returncode=0)

        revert_target(Path("agents/researcher.md"))
        args = mock_run.call_args[0][0]
        assert args == ["git", "checkout", "--", "agents/researcher.md"]

    @patch("autoresearch_engine.subprocess.run")
    def test_commit_improvement_returns_sha(self, mock_run: MagicMock) -> None:
        """commit_improvement should return the commit SHA."""
        # Mock the three subprocess calls: git add, git commit, git rev-parse
        mock_run.side_effect = [
            MagicMock(returncode=0),  # git add
            MagicMock(returncode=0),  # git commit
            MagicMock(returncode=0, stdout="abc123def\n"),  # git rev-parse
        ]

        sha = commit_improvement(Path("agents/researcher.md"), message="improve researcher")
        assert sha == "abc123def"
        assert mock_run.call_count == 3


# ---------------------------------------------------------------------------
# Allowed patterns constant
# ---------------------------------------------------------------------------


class TestAllowedPatterns:
    """Tests for the ALLOWED_TARGET_PATTERNS constant."""

    def test_patterns_exist(self) -> None:
        """Constant should have expected patterns."""
        assert "agents/*.md" in ALLOWED_TARGET_PATTERNS
        assert "skills/*/SKILL.md" in ALLOWED_TARGET_PATTERNS

    def test_patterns_count(self) -> None:
        """Should have exactly 2 patterns."""
        assert len(ALLOWED_TARGET_PATTERNS) == 2
