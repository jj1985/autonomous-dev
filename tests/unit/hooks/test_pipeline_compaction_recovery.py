"""Tests for pipeline context saver and recovery during compaction.

Tests cover:
- pre_compact_batch_saver.sh: pipeline state capture alongside batch state
- unified_prompt_validator.py: pipeline recovery injection from marker
- Existing batch recovery remains unchanged
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
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
SESSION_START_SCRIPT = HOOKS_DIR / "SessionStart-batch-recovery.sh"


def _run_hook(
    script: Path,
    stdin_data: str = "",
    cwd: str = "",
    env_extra: dict = None,
):
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


def _import_validator():
    """Import unified_prompt_validator module dynamically."""
    validator_path = HOOKS_DIR / "unified_prompt_validator.py"
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "unified_prompt_validator", str(validator_path)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_pipeline_per_run_state(
    run_id: str = "test-run-001",
    feature: str = "Add auth system",
    mode: str = "full",
    steps: dict = None,
) -> dict:
    """Create a per-run pipeline state JSON structure."""
    if steps is None:
        steps = {
            "alignment": {"status": "passed", "started_at": None, "completed_at": None, "error": None},
            "research_cache": {"status": "skipped", "started_at": None, "completed_at": None, "error": None},
            "research": {"status": "passed", "started_at": None, "completed_at": None, "error": None},
            "plan": {"status": "passed", "started_at": None, "completed_at": None, "error": None},
            "acceptance_tests": {"status": "running", "started_at": None, "completed_at": None, "error": None},
            "tdd_tests": {"status": "pending", "started_at": None, "completed_at": None, "error": None},
            "implement": {"status": "pending", "started_at": None, "completed_at": None, "error": None},
        }
    return {
        "run_id": run_id,
        "mode": mode,
        "feature": feature,
        "steps": steps,
        "created_at": "2026-04-01T10:00:00+00:00",
        "updated_at": "2026-04-01T10:05:00+00:00",
    }


def _make_signed_state(
    run_id: str = "test-run-001",
    mode: str = "full",
) -> dict:
    """Create a signed pipeline state (implement_pipeline_state.json)."""
    return {
        "session_start": "2026-04-01T10:00:00",
        "mode": mode,
        "run_id": run_id,
        "explicitly_invoked": True,
        "session_id": "test-session",
    }


# ===========================================================================
# TestPreCompactPipelineSaver
# ===========================================================================


class TestPreCompactPipelineSaver:
    """Tests for pipeline state capture in pre_compact_batch_saver.sh."""

    def test_pipeline_state_creates_marker_with_pipeline_field(self, tmp_path):
        """When pipeline state exists, marker is created with a pipeline field."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        # Create signed state file
        signed_state_file = tmp_path / "signed_state.json"
        signed_state_file.write_text(json.dumps(_make_signed_state()))

        # Create per-run state file
        per_run_file = tmp_path / "pipeline_state_test-run-001.json"
        per_run_file.write_text(json.dumps(_make_pipeline_per_run_state()))

        rc, _, _ = _run_hook(
            PRE_COMPACT_SCRIPT,
            cwd=str(tmp_path),
            env_extra={
                "PIPELINE_STATE_FILE": str(signed_state_file),
                "PIPELINE_STATE_DIR": str(tmp_path),
            },
        )
        assert rc == 0

        marker_path = claude_dir / "compaction_recovery.json"
        assert marker_path.exists()

        marker = json.loads(marker_path.read_text())
        assert "pipeline" in marker

    def test_pipeline_field_has_required_keys(self, tmp_path):
        """Pipeline field in marker has all 10 required keys."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        signed_state_file = tmp_path / "signed_state.json"
        signed_state_file.write_text(json.dumps(_make_signed_state()))

        per_run_file = tmp_path / "pipeline_state_test-run-001.json"
        per_run_file.write_text(json.dumps(_make_pipeline_per_run_state()))

        rc, _, _ = _run_hook(
            PRE_COMPACT_SCRIPT,
            cwd=str(tmp_path),
            env_extra={
                "PIPELINE_STATE_FILE": str(signed_state_file),
                "PIPELINE_STATE_DIR": str(tmp_path),
            },
        )
        assert rc == 0

        marker = json.loads((claude_dir / "compaction_recovery.json").read_text())
        pipeline = marker["pipeline"]

        required_keys = {
            "run_id", "feature", "mode", "current_step",
            "steps_completed", "steps_remaining", "modified_files",
            "state_path", "cwd", "saved_at",
        }
        assert set(pipeline.keys()) == required_keys

    def test_current_step_detects_running(self, tmp_path):
        """Step with 'running' status is chosen as current_step."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        signed_state_file = tmp_path / "signed_state.json"
        signed_state_file.write_text(json.dumps(_make_signed_state()))

        steps = {
            "alignment": {"status": "passed", "started_at": None, "completed_at": None, "error": None},
            "research": {"status": "passed", "started_at": None, "completed_at": None, "error": None},
            "plan": {"status": "running", "started_at": None, "completed_at": None, "error": None},
        }
        per_run_file = tmp_path / "pipeline_state_test-run-001.json"
        per_run_file.write_text(json.dumps(_make_pipeline_per_run_state(steps=steps)))

        rc, _, _ = _run_hook(
            PRE_COMPACT_SCRIPT,
            cwd=str(tmp_path),
            env_extra={
                "PIPELINE_STATE_FILE": str(signed_state_file),
                "PIPELINE_STATE_DIR": str(tmp_path),
            },
        )
        assert rc == 0

        marker = json.loads((claude_dir / "compaction_recovery.json").read_text())
        assert marker["pipeline"]["current_step"] == "plan"

    def test_current_step_falls_back_to_last_passed(self, tmp_path):
        """When no running step, last passed step is used as current_step."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        signed_state_file = tmp_path / "signed_state.json"
        signed_state_file.write_text(json.dumps(_make_signed_state()))

        steps = {
            "alignment": {"status": "passed", "started_at": None, "completed_at": None, "error": None},
            "research": {"status": "passed", "started_at": None, "completed_at": None, "error": None},
            "plan": {"status": "pending", "started_at": None, "completed_at": None, "error": None},
        }
        per_run_file = tmp_path / "pipeline_state_test-run-001.json"
        per_run_file.write_text(json.dumps(_make_pipeline_per_run_state(steps=steps)))

        rc, _, _ = _run_hook(
            PRE_COMPACT_SCRIPT,
            cwd=str(tmp_path),
            env_extra={
                "PIPELINE_STATE_FILE": str(signed_state_file),
                "PIPELINE_STATE_DIR": str(tmp_path),
            },
        )
        assert rc == 0

        marker = json.loads((claude_dir / "compaction_recovery.json").read_text())
        assert marker["pipeline"]["current_step"] == "research"

    def test_no_batch_no_pipeline_no_marker(self, tmp_path):
        """When neither batch nor pipeline state exists, no marker is created."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        rc, _, _ = _run_hook(
            PRE_COMPACT_SCRIPT,
            cwd=str(tmp_path),
            env_extra={
                "PIPELINE_STATE_FILE": str(tmp_path / "nonexistent.json"),
                "PIPELINE_STATE_DIR": str(tmp_path),
            },
        )
        assert rc == 0
        assert not (claude_dir / "compaction_recovery.json").exists()

    def test_both_batch_and_pipeline_creates_combined_marker(self, tmp_path):
        """When both batch and pipeline exist, marker has both fields."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        # Create batch state
        batch_state = {
            "batch_id": "batch-combo",
            "status": "in_progress",
            "current_index": 1,
            "total_features": 3,
            "features": ["a", "b", "c"],
        }
        (claude_dir / "batch_state.json").write_text(json.dumps(batch_state))

        # Create pipeline state
        signed_state_file = tmp_path / "signed_state.json"
        signed_state_file.write_text(json.dumps(_make_signed_state()))

        per_run_file = tmp_path / "pipeline_state_test-run-001.json"
        per_run_file.write_text(json.dumps(_make_pipeline_per_run_state()))

        rc, _, _ = _run_hook(
            PRE_COMPACT_SCRIPT,
            cwd=str(tmp_path),
            env_extra={
                "PIPELINE_STATE_FILE": str(signed_state_file),
                "PIPELINE_STATE_DIR": str(tmp_path),
            },
        )
        assert rc == 0

        marker = json.loads((claude_dir / "compaction_recovery.json").read_text())
        assert marker["batch_id"] == "batch-combo"
        assert "pipeline" in marker
        assert marker["pipeline"]["run_id"] == "test-run-001"

    def test_corrupt_pipeline_state_exits_zero(self, tmp_path):
        """Corrupt pipeline state JSON exits 0 without error."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        signed_state_file = tmp_path / "signed_state.json"
        signed_state_file.write_text("not valid json{{{")

        rc, _, _ = _run_hook(
            PRE_COMPACT_SCRIPT,
            cwd=str(tmp_path),
            env_extra={
                "PIPELINE_STATE_FILE": str(signed_state_file),
                "PIPELINE_STATE_DIR": str(tmp_path),
            },
        )
        assert rc == 0

    def test_pipeline_only_no_batch(self, tmp_path):
        """Pipeline only (no batch) creates marker with pipeline field."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        signed_state_file = tmp_path / "signed_state.json"
        signed_state_file.write_text(json.dumps(_make_signed_state()))

        per_run_file = tmp_path / "pipeline_state_test-run-001.json"
        per_run_file.write_text(json.dumps(_make_pipeline_per_run_state()))

        rc, _, _ = _run_hook(
            PRE_COMPACT_SCRIPT,
            cwd=str(tmp_path),
            env_extra={
                "PIPELINE_STATE_FILE": str(signed_state_file),
                "PIPELINE_STATE_DIR": str(tmp_path),
            },
        )
        assert rc == 0

        marker = json.loads((claude_dir / "compaction_recovery.json").read_text())
        assert "pipeline" in marker
        # No batch_id at top level
        assert "batch_id" not in marker


# ===========================================================================
# TestPipelineRecoveryInjection
# ===========================================================================


class TestPipelineRecoveryInjection:
    """Tests for pipeline recovery injection in unified_prompt_validator.py."""

    def test_pipeline_only_marker_produces_recovery_context(self, tmp_path):
        """Marker with pipeline field only produces pipeline recovery context."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        marker = {
            "saved_at": now,
            "pipeline": {
                "run_id": "run-abc",
                "feature": "Add auth system",
                "mode": "full",
                "current_step": "implement",
                "steps_completed": 5,
                "steps_remaining": 8,
                "modified_files": ["src/auth.py", "tests/test_auth.py"],
                "state_path": "/tmp/pipeline_state_run-abc.json",
                "cwd": str(tmp_path),
                "saved_at": now,
            },
        }
        (claude_dir / "compaction_recovery.json").write_text(json.dumps(marker))

        module = _import_validator()

        with patch.object(os, "getcwd", return_value=str(tmp_path)):
            captured = StringIO()
            with patch("sys.stderr", captured):
                module._check_compaction_recovery()

        output = captured.getvalue()
        assert "PIPELINE STATE RECOVERED AFTER COMPACTION" in output
        assert "run-abc" in output
        assert "Add auth system" in output
        assert "implement" in output

    def test_pipeline_context_includes_modified_files(self, tmp_path):
        """Modified files are listed in pipeline recovery output."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        marker = {
            "saved_at": now,
            "pipeline": {
                "run_id": "run-files",
                "feature": "Test feature",
                "mode": "full",
                "current_step": "validate",
                "steps_completed": 7,
                "steps_remaining": 6,
                "modified_files": ["src/main.py", "lib/utils.py"],
                "state_path": "/tmp/pipeline_state_run-files.json",
                "cwd": str(tmp_path),
                "saved_at": now,
            },
        }
        (claude_dir / "compaction_recovery.json").write_text(json.dumps(marker))

        module = _import_validator()

        with patch.object(os, "getcwd", return_value=str(tmp_path)):
            captured = StringIO()
            with patch("sys.stderr", captured):
                module._check_compaction_recovery()

        output = captured.getvalue()
        assert "src/main.py" in output
        assert "lib/utils.py" in output

    def test_stale_pipeline_discarded(self, tmp_path):
        """Pipeline saved_at >900s old is discarded."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        old_time = (datetime.now(timezone.utc) - timedelta(seconds=1000)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        marker = {
            "saved_at": old_time,
            "pipeline": {
                "run_id": "run-stale",
                "feature": "Stale feature",
                "mode": "full",
                "current_step": "plan",
                "steps_completed": 2,
                "steps_remaining": 11,
                "modified_files": [],
                "state_path": "/tmp/pipeline_state_run-stale.json",
                "cwd": str(tmp_path),
                "saved_at": old_time,
            },
        }
        (claude_dir / "compaction_recovery.json").write_text(json.dumps(marker))

        module = _import_validator()

        with patch.object(os, "getcwd", return_value=str(tmp_path)):
            captured = StringIO()
            with patch("sys.stderr", captured):
                module._check_compaction_recovery()

        output = captured.getvalue()
        assert "PIPELINE STATE RECOVERED" not in output

    def test_cwd_mismatch_skips_pipeline(self, tmp_path):
        """Different cwd means pipeline recovery is skipped."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        marker = {
            "saved_at": now,
            "pipeline": {
                "run_id": "run-cwd",
                "feature": "Wrong dir feature",
                "mode": "full",
                "current_step": "research",
                "steps_completed": 1,
                "steps_remaining": 12,
                "modified_files": [],
                "state_path": "/tmp/pipeline_state_run-cwd.json",
                "cwd": "/some/other/directory",
                "saved_at": now,
            },
        }
        (claude_dir / "compaction_recovery.json").write_text(json.dumps(marker))

        module = _import_validator()

        with patch.object(os, "getcwd", return_value=str(tmp_path)):
            captured = StringIO()
            with patch("sys.stderr", captured):
                module._check_compaction_recovery()

        output = captured.getvalue()
        assert "PIPELINE STATE RECOVERED" not in output

    def test_batch_and_pipeline_both_shown(self, tmp_path):
        """When both batch and pipeline exist, both sections appear."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        marker = {
            "batch_id": "batch-dual",
            "status": "in_progress",
            "current_index": 0,
            "total_features": 3,
            "features": ["alpha", "beta", "gamma"],
            "checkpoint": {"completed_features": [], "failed_features": []},
            "saved_at": now,
            "compact_summary": "",
            "pipeline": {
                "run_id": "run-dual",
                "feature": "Alpha feature",
                "mode": "full",
                "current_step": "implement",
                "steps_completed": 5,
                "steps_remaining": 8,
                "modified_files": [],
                "state_path": "/tmp/pipeline_state_run-dual.json",
                "cwd": str(tmp_path),
                "saved_at": now,
            },
        }
        (claude_dir / "compaction_recovery.json").write_text(json.dumps(marker))

        module = _import_validator()

        with patch.object(os, "getcwd", return_value=str(tmp_path)):
            captured = StringIO()
            with patch("sys.stderr", captured):
                module._check_compaction_recovery()

        output = captured.getvalue()
        assert "BATCH STATE RECOVERED AFTER COMPACTION" in output
        assert "PIPELINE STATE RECOVERED AFTER COMPACTION" in output
        assert "batch-dual" in output
        assert "run-dual" in output

    def test_marker_deleted_after_pipeline_recovery(self, tmp_path):
        """Marker file is deleted after pipeline recovery processing."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        marker = {
            "saved_at": now,
            "pipeline": {
                "run_id": "run-del",
                "feature": "Delete test",
                "mode": "full",
                "current_step": "plan",
                "steps_completed": 2,
                "steps_remaining": 11,
                "modified_files": [],
                "state_path": "/tmp/pipeline_state_run-del.json",
                "cwd": str(tmp_path),
                "saved_at": now,
            },
        }
        marker_path = claude_dir / "compaction_recovery.json"
        marker_path.write_text(json.dumps(marker))

        module = _import_validator()

        with patch.object(os, "getcwd", return_value=str(tmp_path)):
            with patch("sys.stderr", StringIO()):
                module._check_compaction_recovery()

        assert not marker_path.exists()

    def test_pipeline_recovery_includes_resume_instruction(self, tmp_path):
        """Output includes 'Resume /implement' instruction."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        marker = {
            "saved_at": now,
            "pipeline": {
                "run_id": "run-resume",
                "feature": "Resume test",
                "mode": "full",
                "current_step": "validate",
                "steps_completed": 7,
                "steps_remaining": 6,
                "modified_files": [],
                "state_path": "/tmp/pipeline_state_run-resume.json",
                "cwd": str(tmp_path),
                "saved_at": now,
            },
        }
        (claude_dir / "compaction_recovery.json").write_text(json.dumps(marker))

        module = _import_validator()

        with patch.object(os, "getcwd", return_value=str(tmp_path)):
            captured = StringIO()
            with patch("sys.stderr", captured):
                module._check_compaction_recovery()

        output = captured.getvalue()
        assert "Resume /implement" in output


# ===========================================================================
# TestExistingBatchRecoveryUnchanged
# ===========================================================================


class TestExistingBatchRecoveryUnchanged:
    """Verify existing batch-only recovery still works."""

    def test_batch_only_marker_still_works(self, tmp_path):
        """Batch-only marker (no pipeline field) produces batch recovery context."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        marker = {
            "batch_id": "batch-legacy",
            "status": "in_progress",
            "current_index": 2,
            "total_features": 5,
            "features": ["a", "b", "c", "d", "e"],
            "checkpoint": {
                "completed_features": ["a", "b"],
                "failed_features": [],
            },
            "saved_at": "2026-04-01T10:00:00Z",
            "compact_summary": "Working on feature c",
        }
        (claude_dir / "compaction_recovery.json").write_text(json.dumps(marker))

        module = _import_validator()

        with patch.object(os, "getcwd", return_value=str(tmp_path)):
            captured = StringIO()
            with patch("sys.stderr", captured):
                module._check_compaction_recovery()

        output = captured.getvalue()
        assert "BATCH STATE RECOVERED AFTER COMPACTION" in output
        assert "batch-legacy" in output
        assert "Feature 3 of 5" in output
        assert "Completed: 2" in output
        assert "c" in output
        assert "Working on feature c" in output
        # No pipeline section
        assert "PIPELINE STATE RECOVERED" not in output
