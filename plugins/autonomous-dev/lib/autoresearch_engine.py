"""Autonomous experiment loop engine for /autoresearch command.

Provides experiment loop mechanics: target validation, metric execution,
experiment history tracking, and stall detection.

GitHub Issue: #654
"""

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

ALLOWED_TARGET_PATTERNS = ["agents/*.md", "skills/*/SKILL.md"]


@dataclass
class ExperimentConfig:
    """Configuration for an autoresearch experiment loop.

    Args:
        target: Path to the file being optimized (must match whitelist)
        metric_script: Path to the benchmark script that outputs METRIC: <float>
        iterations: Maximum number of experiment iterations
        min_improvement: Minimum metric improvement to count as success
        dry_run: If True, skip git operations (commit/branch)
        experiment_branch: Override branch name (auto-generated if empty)
        max_stall: Maximum consecutive failures before halting
    """

    target: Path
    metric_script: Path
    iterations: int = 20
    min_improvement: float = 0.01
    dry_run: bool = False
    experiment_branch: str = ""
    max_stall: int = 3


def validate_target(target: Path, *, repo_root: Path) -> Tuple[bool, str]:
    """Check target file is in the allowed whitelist.

    Only files matching agents/*.md or skills/*/SKILL.md are allowed
    to prevent uncontrolled modifications to arbitrary files.

    Args:
        target: Path to the target file (absolute or relative)
        repo_root: Repository root for resolving relative paths

    Returns:
        Tuple of (is_valid, error_message). error_message is empty on success.
    """
    try:
        resolved = target.resolve()
        resolved_root = repo_root.resolve()

        # Security: ensure target is within repo
        try:
            resolved.relative_to(resolved_root)
        except ValueError:
            return (False, f"Target {target} is outside repository root {repo_root}")

        # Get relative path from repo root for pattern matching
        rel_path = str(resolved.relative_to(resolved_root))
    except (OSError, ValueError) as e:
        return (False, f"Cannot resolve target path: {e}")

    for pattern in ALLOWED_TARGET_PATTERNS:
        # Use PurePosixPath.match for proper glob semantics (** needed for recursive)
        if PurePosixPath(rel_path).match(pattern):
            if not resolved.exists():
                return (False, f"Target file does not exist: {target}")
            return (True, "")

    return (
        False,
        f"Target {rel_path} does not match allowed patterns: {ALLOWED_TARGET_PATTERNS}\n"
        f"Allowed: agents/*.md, skills/*/SKILL.md",
    )


def validate_metric(metric_script: Path) -> Tuple[bool, str]:
    """Check that the metric script exists and is a file.

    Args:
        metric_script: Path to the benchmark/metric script

    Returns:
        Tuple of (is_valid, error_message). error_message is empty on success.
    """
    if not metric_script.exists():
        return (False, f"Metric script not found: {metric_script}")
    if not metric_script.is_file():
        return (False, f"Metric script is not a file: {metric_script}")
    return (True, "")


def run_metric(metric_script: Path, *, timeout: int = 300) -> Tuple[float, str]:
    """Run a benchmark script and parse the METRIC: <float> output.

    The script must output a line matching 'METRIC: <float>' to stdout or stderr.
    The last such line is used if multiple are present.

    Args:
        metric_script: Path to the executable benchmark script
        timeout: Maximum seconds to wait for the script (default: 300)

    Returns:
        Tuple of (metric_value, raw_output).

    Raises:
        ValueError: If no METRIC line found or metric is not a valid float
        subprocess.TimeoutExpired: If script exceeds timeout
        subprocess.CalledProcessError: If script exits with non-zero code
    """
    result = subprocess.run(
        ["python3", str(metric_script)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    combined_output = result.stdout + "\n" + result.stderr
    metric_pattern = re.compile(r"^METRIC:\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)$", re.MULTILINE)
    matches = metric_pattern.findall(combined_output)

    if not matches:
        raise ValueError(
            f"No 'METRIC: <float>' line found in script output.\n"
            f"Script: {metric_script}\n"
            f"Output: {combined_output[:500]}"
        )

    try:
        value = float(matches[-1])
    except ValueError:
        raise ValueError(
            f"Could not parse metric value as float: {matches[-1]!r}\n"
            f"Script: {metric_script}"
        )

    return (value, combined_output)


def create_experiment_branch(target_name: str) -> str:
    """Create a git branch for the experiment.

    Branch name format: autoresearch/<target_name>-<timestamp>

    Args:
        target_name: Short name derived from the target file

    Returns:
        The branch name that was created.

    Raises:
        subprocess.CalledProcessError: If git checkout fails
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    # Sanitize target name for branch naming
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "-", target_name)
    branch_name = f"autoresearch/{safe_name}-{timestamp}"

    subprocess.run(
        ["git", "checkout", "-b", branch_name],
        capture_output=True,
        text=True,
        check=True,
    )

    return branch_name


def revert_target(target: Path) -> None:
    """Revert a target file to its last committed state.

    Args:
        target: Path to the file to revert

    Raises:
        subprocess.CalledProcessError: If git checkout fails
    """
    subprocess.run(
        ["git", "checkout", "--", str(target)],
        capture_output=True,
        text=True,
        check=True,
    )


def commit_improvement(target: Path, *, message: str) -> str:
    """Stage and commit an improvement to the target file.

    Args:
        target: Path to the improved file
        message: Commit message describing the improvement

    Returns:
        The commit SHA.

    Raises:
        subprocess.CalledProcessError: If git add or commit fails
    """
    subprocess.run(
        ["git", "add", str(target)],
        capture_output=True,
        text=True,
        check=True,
    )

    subprocess.run(
        ["git", "commit", "-m", message],
        capture_output=True,
        text=True,
        check=True,
    )

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout.strip()


class ExperimentHistory:
    """Append-only JSONL experiment log.

    Tracks hypothesis, before/after metrics, and outcomes for each
    experiment iteration. Tolerates corrupt lines on read.

    Args:
        path: Path to the JSONL history file
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        """The path to the history file."""
        return self._path

    def append(
        self,
        *,
        hypothesis: str,
        metric_before: float,
        metric_after: float,
        outcome: str,
    ) -> None:
        """Append an experiment result to the history file.

        Args:
            hypothesis: The hypothesis being tested
            metric_before: Metric value before the experiment
            metric_after: Metric value after the experiment
            outcome: One of 'improved', 'reverted', 'error'
        """
        entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hypothesis": hypothesis,
            "metric_before": metric_before,
            "metric_after": metric_after,
            "outcome": outcome,
            "delta": metric_after - metric_before,
        }

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def load_all(self) -> List[Dict[str, Any]]:
        """Load all entries from the history file.

        Corrupt or unparseable lines are silently skipped.

        Returns:
            List of all valid history entries, oldest first.
        """
        if not self._path.exists():
            return []

        entries: List[Dict[str, Any]] = []
        for line in self._path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                print(
                    f"Warning: Skipping corrupt history line in {self._path}",
                    file=sys.stderr,
                )
        return entries

    def load_recent(self, n: int = 10) -> List[Dict[str, Any]]:
        """Load the most recent N entries.

        Args:
            n: Number of recent entries to return (default: 10)

        Returns:
            List of up to N most recent entries, newest first.
        """
        all_entries = self.load_all()
        return list(reversed(all_entries[-n:]))

    def consecutive_failures(self) -> int:
        """Count consecutive non-improved outcomes from the end.

        Returns:
            Number of consecutive entries where outcome != 'improved'.
        """
        entries = self.load_all()
        count = 0
        for entry in reversed(entries):
            if entry.get("outcome") == "improved":
                break
            count += 1
        return count

    def summary(self) -> Dict[str, Any]:
        """Generate a summary of the experiment history.

        Returns:
            Dict with total, improved, reverted, error counts and best/worst deltas.
        """
        entries = self.load_all()
        if not entries:
            return {
                "total": 0,
                "improved": 0,
                "reverted": 0,
                "error": 0,
                "best_delta": 0.0,
                "worst_delta": 0.0,
            }

        outcomes = [e.get("outcome", "unknown") for e in entries]
        deltas = [e.get("delta", 0.0) for e in entries]

        return {
            "total": len(entries),
            "improved": outcomes.count("improved"),
            "reverted": outcomes.count("reverted"),
            "error": outcomes.count("error"),
            "best_delta": max(deltas) if deltas else 0.0,
            "worst_delta": min(deltas) if deltas else 0.0,
        }


def check_stall(history: ExperimentHistory, *, max_consecutive: int = 3) -> bool:
    """Check if the experiment loop has stalled.

    Stalled means N consecutive iterations failed to improve the metric.

    Args:
        history: The experiment history to check
        max_consecutive: Maximum allowed consecutive failures (default: 3)

    Returns:
        True if stalled (consecutive failures >= max_consecutive), False otherwise.
    """
    return history.consecutive_failures() >= max_consecutive
