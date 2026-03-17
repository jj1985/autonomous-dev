"""Tests for PreCompact/PostCompact batch state preservation hooks.

Tests cover:
- pre_compact_batch_saver.sh: marker creation when batch active
- post_compact_enricher.sh: marker enrichment with compact summary
- unified_prompt_validator.py: recovery injection from marker
"""

import json
import os
import subprocess
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WORKTREE = Path(__file__).resolve().parents[3]
HOOKS_DIR = WORKTREE / "plugins" / "autonomous-dev" / "hooks"
PRE_COMPACT_SCRIPT = HOOKS_DIR / "pre_compact_batch_saver.sh"
POST_COMPACT_SCRIPT = HOOKS_DIR / "post_compact_enricher.sh"


def _run_hook(script: Path, stdin_data: str = "", cwd: str = "", env_extra: dict = None):
    """Run a bash hook script and return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        ["bash", str(script)],
        input=stdin_data,
        capture_output=True,
        text=True,
        cwd=cwd or str(WORKTREE),
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


# ===========================================================================
# PreCompact batch saver tests
# ===========================================================================


class TestPreCompactBatchSaver:
    """Tests for pre_compact_batch_saver.sh."""

    def test_no_batch_state_no_marker(self, tmp_path):
        """When no batch_state.json exists, no marker is created."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        rc, _, _ = _run_hook(PRE_COMPACT_SCRIPT, cwd=str(tmp_path))
        assert rc == 0
        assert not (claude_dir / "compaction_recovery.json").exists()

    def test_batch_not_in_progress_no_marker(self, tmp_path):
        """When batch status is not in_progress, no marker is created."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "batch_state.json").write_text(json.dumps({
            "batch_id": "test-batch",
            "status": "completed",
            "current_index": 0,
            "total_features": 3,
            "features": [],
        }))

        rc, _, _ = _run_hook(PRE_COMPACT_SCRIPT, cwd=str(tmp_path))
        assert rc == 0
        assert not (claude_dir / "compaction_recovery.json").exists()

    def test_active_batch_creates_marker(self, tmp_path):
        """When batch is in_progress, marker is created with correct structure."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        batch_state = {
            "batch_id": "batch-123",
            "status": "in_progress",
            "current_index": 2,
            "total_features": 5,
            "features": ["feat-A", "feat-B", "feat-C", "feat-D", "feat-E"],
        }
        (claude_dir / "batch_state.json").write_text(json.dumps(batch_state))

        rc, _, _ = _run_hook(PRE_COMPACT_SCRIPT, cwd=str(tmp_path))
        assert rc == 0

        marker_path = claude_dir / "compaction_recovery.json"
        assert marker_path.exists()

        marker = json.loads(marker_path.read_text())
        assert marker["batch_id"] == "batch-123"
        assert marker["status"] == "in_progress"
        assert marker["current_index"] == 2
        assert marker["total_features"] == 5
        assert marker["features"] == ["feat-A", "feat-B", "feat-C", "feat-D", "feat-E"]
        assert marker["compact_summary"] == ""
        assert "saved_at" in marker

    def test_active_batch_with_checkpoint(self, tmp_path):
        """When RALPH checkpoint exists, it is included in the marker."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        batch_state = {
            "batch_id": "batch-456",
            "status": "in_progress",
            "current_index": 1,
            "total_features": 3,
            "features": ["a", "b", "c"],
        }
        (claude_dir / "batch_state.json").write_text(json.dumps(batch_state))

        # Create RALPH checkpoint
        checkpoint_dir = tmp_path / ".ralph-checkpoints"
        checkpoint_dir.mkdir()
        checkpoint_data = {
            "completed_features": ["a"],
            "failed_features": [],
            "current_feature_index": 1,
        }
        (checkpoint_dir / "ralph-batch-456_checkpoint.json").write_text(
            json.dumps(checkpoint_data)
        )

        rc, _, _ = _run_hook(PRE_COMPACT_SCRIPT, cwd=str(tmp_path))
        assert rc == 0

        marker = json.loads((claude_dir / "compaction_recovery.json").read_text())
        assert marker["checkpoint"]["completed_features"] == ["a"]
        assert marker["checkpoint"]["current_feature_index"] == 1

    def test_always_exits_zero(self, tmp_path):
        """Hook always exits 0 even with corrupt state."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        # Write corrupt JSON
        (claude_dir / "batch_state.json").write_text("not valid json{{{")

        rc, _, _ = _run_hook(PRE_COMPACT_SCRIPT, cwd=str(tmp_path))
        assert rc == 0


# ===========================================================================
# PostCompact enricher tests
# ===========================================================================


class TestPostCompactEnricher:
    """Tests for post_compact_enricher.sh."""

    def test_no_marker_noop(self, tmp_path):
        """When no recovery marker exists, does nothing."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        rc, _, _ = _run_hook(
            POST_COMPACT_SCRIPT,
            stdin_data='{"compact_summary": "test summary"}',
            cwd=str(tmp_path),
        )
        assert rc == 0

    def test_enriches_marker_with_summary(self, tmp_path):
        """Updates marker with compact_summary from stdin."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        marker = {
            "batch_id": "batch-789",
            "status": "in_progress",
            "current_index": 0,
            "total_features": 2,
            "features": ["x", "y"],
            "checkpoint": {},
            "saved_at": "2026-01-01T00:00:00Z",
            "compact_summary": "",
        }
        marker_path = claude_dir / "compaction_recovery.json"
        marker_path.write_text(json.dumps(marker))

        summary_text = "Session was working on batch processing feature X"
        rc, _, _ = _run_hook(
            POST_COMPACT_SCRIPT,
            stdin_data=json.dumps({"compact_summary": summary_text}),
            cwd=str(tmp_path),
        )
        assert rc == 0

        updated = json.loads(marker_path.read_text())
        assert updated["compact_summary"] == summary_text
        # Other fields preserved
        assert updated["batch_id"] == "batch-789"

    def test_no_summary_in_stdin_preserves_marker(self, tmp_path):
        """When stdin has no compact_summary, marker is unchanged."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        marker = {
            "batch_id": "batch-abc",
            "compact_summary": "",
        }
        marker_path = claude_dir / "compaction_recovery.json"
        marker_path.write_text(json.dumps(marker))

        rc, _, _ = _run_hook(
            POST_COMPACT_SCRIPT,
            stdin_data="{}",
            cwd=str(tmp_path),
        )
        assert rc == 0

        updated = json.loads(marker_path.read_text())
        assert updated["compact_summary"] == ""

    def test_always_exits_zero(self, tmp_path):
        """Hook always exits 0 even with bad input."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "compaction_recovery.json").write_text("corrupt{{{")

        rc, _, _ = _run_hook(
            POST_COMPACT_SCRIPT,
            stdin_data="not json either",
            cwd=str(tmp_path),
        )
        assert rc == 0


# ===========================================================================
# Recovery injection tests (unified_prompt_validator.py)
# ===========================================================================


class TestCompactionRecoveryInjection:
    """Tests for _check_compaction_recovery in unified_prompt_validator.py."""

    def _import_validator(self):
        """Import the validator module dynamically."""
        validator_path = HOOKS_DIR / "unified_prompt_validator.py"
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "unified_prompt_validator", str(validator_path)
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_no_marker_no_output(self, tmp_path):
        """When no marker exists, no output is produced."""
        module = self._import_validator()

        with patch.object(os, "getcwd", return_value=str(tmp_path)):
            captured = StringIO()
            with patch("sys.stderr", captured):
                module._check_compaction_recovery()

        assert captured.getvalue() == ""

    def test_marker_produces_recovery_context(self, tmp_path):
        """When marker exists, recovery context is printed to stderr."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        marker = {
            "batch_id": "batch-recovery-test",
            "status": "in_progress",
            "current_index": 1,
            "total_features": 4,
            "features": ["alpha", "beta", "gamma", "delta"],
            "checkpoint": {
                "completed_features": ["alpha"],
                "failed_features": [],
            },
            "saved_at": "2026-01-01T00:00:00Z",
            "compact_summary": "Was implementing beta feature",
        }
        (claude_dir / "compaction_recovery.json").write_text(json.dumps(marker))

        module = self._import_validator()

        with patch.object(os, "getcwd", return_value=str(tmp_path)):
            captured = StringIO()
            with patch("sys.stderr", captured):
                module._check_compaction_recovery()

        output = captured.getvalue()
        assert "BATCH STATE RECOVERED AFTER COMPACTION" in output
        assert "batch-recovery-test" in output
        assert "Feature 2 of 4" in output
        assert "Completed: 1" in output
        assert "Failed: 0" in output
        assert "beta" in output
        assert "Was implementing beta feature" in output

    def test_marker_deleted_after_processing(self, tmp_path):
        """Marker file is deleted after successful processing."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        marker = {
            "batch_id": "del-test",
            "status": "in_progress",
            "current_index": 0,
            "total_features": 1,
            "features": ["only-one"],
            "checkpoint": {},
            "saved_at": "2026-01-01T00:00:00Z",
            "compact_summary": "",
        }
        marker_path = claude_dir / "compaction_recovery.json"
        marker_path.write_text(json.dumps(marker))

        module = self._import_validator()

        with patch.object(os, "getcwd", return_value=str(tmp_path)):
            with patch("sys.stderr", StringIO()):
                module._check_compaction_recovery()

        assert not marker_path.exists()

    def test_corrupt_marker_handled_gracefully(self, tmp_path):
        """Corrupt marker is handled without raising and gets deleted."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        marker_path = claude_dir / "compaction_recovery.json"
        marker_path.write_text("not valid json at all{{{")

        module = self._import_validator()

        with patch.object(os, "getcwd", return_value=str(tmp_path)):
            with patch("sys.stderr", StringIO()):
                # Should not raise
                module._check_compaction_recovery()

        # Corrupt marker should be cleaned up
        assert not marker_path.exists()

    def test_features_as_dicts(self, tmp_path):
        """Features can be dicts with description/title keys."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        marker = {
            "batch_id": "dict-features",
            "status": "in_progress",
            "current_index": 0,
            "total_features": 2,
            "features": [
                {"description": "Add auth system", "title": "Auth"},
                {"title": "Logging"},
            ],
            "checkpoint": {},
            "saved_at": "2026-01-01T00:00:00Z",
            "compact_summary": "",
        }
        (claude_dir / "compaction_recovery.json").write_text(json.dumps(marker))

        module = self._import_validator()

        with patch.object(os, "getcwd", return_value=str(tmp_path)):
            captured = StringIO()
            with patch("sys.stderr", captured):
                module._check_compaction_recovery()

        output = captured.getvalue()
        assert "Add auth system" in output

    def test_no_compact_summary_omits_section(self, tmp_path):
        """When compact_summary is empty, that section is omitted."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        marker = {
            "batch_id": "no-summary",
            "status": "in_progress",
            "current_index": 0,
            "total_features": 1,
            "features": ["feat"],
            "checkpoint": {},
            "saved_at": "2026-01-01T00:00:00Z",
            "compact_summary": "",
        }
        (claude_dir / "compaction_recovery.json").write_text(json.dumps(marker))

        module = self._import_validator()

        with patch.object(os, "getcwd", return_value=str(tmp_path)):
            captured = StringIO()
            with patch("sys.stderr", captured):
                module._check_compaction_recovery()

        output = captured.getvalue()
        assert "Compaction Summary:" not in output
