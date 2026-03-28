"""Append-only JSONL storage for timestamped benchmark results.

Stores benchmark scoring reports as one JSON object per line,
enabling trend analysis and improvement loop tracking.

GitHub Issue: #578
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class BenchmarkHistory:
    """Append-only JSONL storage for benchmark results.

    Each line is a self-contained JSON object with timestamp, metrics,
    and optional metadata. Corrupt lines are silently skipped on read.

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
        report: Any,
        *,
        prompt_hash: str,
        model: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append a scoring report to the history file.

        Args:
            report: A ScoringReport instance with benchmark metrics
            prompt_hash: SHA256 hash of the reviewer prompt used
            model: Model identifier used for the benchmark
            metadata: Optional additional metadata to store
        """
        entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt_hash": prompt_hash,
            "model": model,
            "balanced_accuracy": report.balanced_accuracy,
            "false_positive_rate": report.false_positive_rate,
            "false_negative_rate": report.false_negative_rate,
            "per_defect_category": report.per_defect_category,
            "per_difficulty": getattr(report, "per_difficulty", {}),
            "confusion_matrix": report.confusion_matrix,
        }
        if metadata:
            entry["metadata"] = metadata

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def load_all(self) -> List[Dict[str, Any]]:
        """Load all entries from the history file.

        Corrupt or unparseable lines are silently skipped.

        Returns:
            List of all valid history entries, oldest first
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

    def load_latest(self, n: int = 1) -> List[Dict[str, Any]]:
        """Load the most recent N entries.

        Args:
            n: Number of recent entries to return (default: 1)

        Returns:
            List of up to N most recent entries, newest first
        """
        all_entries = self.load_all()
        return list(reversed(all_entries[-n:]))

    def trend(
        self,
        metric: str = "balanced_accuracy",
        *,
        last_n: int = 10,
    ) -> List[Tuple[str, float]]:
        """Extract a trend of (timestamp, metric_value) pairs.

        Args:
            metric: The metric key to extract from each entry
            last_n: Number of most recent entries to include

        Returns:
            List of (timestamp, value) tuples, oldest first
        """
        all_entries = self.load_all()
        recent = all_entries[-last_n:]
        result: List[Tuple[str, float]] = []
        for entry in recent:
            ts = entry.get("timestamp", "")
            value = entry.get(metric)
            if value is not None:
                try:
                    result.append((ts, float(value)))
                except (TypeError, ValueError):
                    continue
        return result


def compute_prompt_hash(prompt_text: str) -> str:
    """Compute a SHA256 hash of reviewer prompt text.

    Args:
        prompt_text: The reviewer prompt/instructions text

    Returns:
        Hex-encoded SHA256 hash string
    """
    return hashlib.sha256(prompt_text.encode()).hexdigest()
