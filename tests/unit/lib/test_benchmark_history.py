"""Unit tests for benchmark_history module.

Tests append-only JSONL storage, loading, trend extraction,
and corrupt line handling.

GitHub Issue: #578
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import pytest

# Add lib to path
_LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(_LIB_DIR))

from benchmark_history import BenchmarkHistory, compute_prompt_hash


@dataclass
class FakeScoringReport:
    """Minimal ScoringReport stub for testing."""

    balanced_accuracy: float = 0.85
    false_positive_rate: float = 0.10
    false_negative_rate: float = 0.15
    per_defect_category: Dict[str, Any] = field(default_factory=dict)
    per_difficulty: Dict[str, Any] = field(default_factory=dict)
    confusion_matrix: Dict[str, int] = field(
        default_factory=lambda: {"TP": 10, "TN": 5, "FP": 2, "FN": 3}
    )


class TestBenchmarkHistoryAppend:
    """Tests for the append method."""

    def test_append_creates_file(self, tmp_path: Path) -> None:
        """Appending to a non-existent file creates it."""
        history_path = tmp_path / "history.jsonl"
        history = BenchmarkHistory(history_path)
        report = FakeScoringReport()

        history.append(report, prompt_hash="abc123", model="test-model")

        assert history_path.exists()
        lines = history_path.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["balanced_accuracy"] == 0.85
        assert entry["prompt_hash"] == "abc123"
        assert entry["model"] == "test-model"

    def test_append_multiple(self, tmp_path: Path) -> None:
        """Multiple appends produce multiple JSONL lines."""
        history_path = tmp_path / "history.jsonl"
        history = BenchmarkHistory(history_path)

        for i in range(3):
            report = FakeScoringReport(balanced_accuracy=0.80 + i * 0.05)
            history.append(report, prompt_hash=f"hash_{i}", model="test-model")

        lines = history_path.read_text().strip().splitlines()
        assert len(lines) == 3

    def test_append_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Append creates parent directories if they don't exist."""
        history_path = tmp_path / "sub" / "dir" / "history.jsonl"
        history = BenchmarkHistory(history_path)
        report = FakeScoringReport()

        history.append(report, prompt_hash="hash", model="model")

        assert history_path.exists()

    def test_append_stores_metadata(self, tmp_path: Path) -> None:
        """Optional metadata is stored when provided."""
        history_path = tmp_path / "history.jsonl"
        history = BenchmarkHistory(history_path)
        report = FakeScoringReport()

        history.append(
            report,
            prompt_hash="hash",
            model="model",
            metadata={"phase": "baseline", "trials": 5},
        )

        entry = json.loads(history_path.read_text().strip())
        assert entry["metadata"]["phase"] == "baseline"
        assert entry["metadata"]["trials"] == 5


class TestBenchmarkHistoryLoad:
    """Tests for load_all and load_latest."""

    def test_load_all_empty_history(self, tmp_path: Path) -> None:
        """Loading from non-existent file returns empty list."""
        history = BenchmarkHistory(tmp_path / "missing.jsonl")
        assert history.load_all() == []

    def test_load_all(self, tmp_path: Path) -> None:
        """load_all returns all entries in order."""
        history_path = tmp_path / "history.jsonl"
        history = BenchmarkHistory(history_path)

        for i in range(5):
            report = FakeScoringReport(balanced_accuracy=0.70 + i * 0.05)
            history.append(report, prompt_hash=f"h{i}", model="m")

        entries = history.load_all()
        assert len(entries) == 5
        assert entries[0]["balanced_accuracy"] == 0.70
        assert entries[4]["balanced_accuracy"] == pytest.approx(0.90)

    def test_load_latest(self, tmp_path: Path) -> None:
        """load_latest returns N most recent entries, newest first."""
        history_path = tmp_path / "history.jsonl"
        history = BenchmarkHistory(history_path)

        for i in range(5):
            report = FakeScoringReport(balanced_accuracy=0.70 + i * 0.05)
            history.append(report, prompt_hash=f"h{i}", model="m")

        latest = history.load_latest(n=2)
        assert len(latest) == 2
        # Newest first
        assert latest[0]["balanced_accuracy"] == pytest.approx(0.90)
        assert latest[1]["balanced_accuracy"] == pytest.approx(0.85)

    def test_corrupt_line_skipped(self, tmp_path: Path) -> None:
        """Corrupt JSONL lines are silently skipped."""
        history_path = tmp_path / "history.jsonl"
        # Write valid, corrupt, valid lines
        lines = [
            json.dumps({"timestamp": "t1", "balanced_accuracy": 0.80}),
            "NOT VALID JSON {{{",
            json.dumps({"timestamp": "t3", "balanced_accuracy": 0.90}),
        ]
        history_path.write_text("\n".join(lines) + "\n")

        history = BenchmarkHistory(history_path)
        entries = history.load_all()
        assert len(entries) == 2
        assert entries[0]["balanced_accuracy"] == 0.80
        assert entries[1]["balanced_accuracy"] == 0.90

    def test_prompt_hash_stored(self, tmp_path: Path) -> None:
        """prompt_hash is stored in each entry."""
        history_path = tmp_path / "history.jsonl"
        history = BenchmarkHistory(history_path)
        report = FakeScoringReport()

        history.append(report, prompt_hash="sha256_abc", model="test")

        entries = history.load_all()
        assert entries[0]["prompt_hash"] == "sha256_abc"


class TestBenchmarkHistoryTrend:
    """Tests for the trend method."""

    def test_trend_extraction(self, tmp_path: Path) -> None:
        """trend() extracts (timestamp, metric) pairs."""
        history_path = tmp_path / "history.jsonl"
        history = BenchmarkHistory(history_path)

        for i in range(5):
            report = FakeScoringReport(balanced_accuracy=0.70 + i * 0.05)
            history.append(report, prompt_hash=f"h{i}", model="m")

        trend = history.trend(metric="balanced_accuracy", last_n=3)
        assert len(trend) == 3
        # Values should be the last 3, oldest first
        assert trend[0][1] == pytest.approx(0.80)
        assert trend[2][1] == pytest.approx(0.90)

    def test_trend_empty_history(self, tmp_path: Path) -> None:
        """trend() on empty history returns empty list."""
        history = BenchmarkHistory(tmp_path / "missing.jsonl")
        assert history.trend() == []


class TestComputePromptHash:
    """Tests for the compute_prompt_hash utility."""

    def test_returns_hex_string(self) -> None:
        """Hash is a hex string of expected length."""
        result = compute_prompt_hash("test prompt")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA256 hex digest

    def test_deterministic(self) -> None:
        """Same input produces same hash."""
        h1 = compute_prompt_hash("hello world")
        h2 = compute_prompt_hash("hello world")
        assert h1 == h2

    def test_different_inputs(self) -> None:
        """Different inputs produce different hashes."""
        h1 = compute_prompt_hash("input A")
        h2 = compute_prompt_hash("input B")
        assert h1 != h2
