"""Regression tests for Issue #869: run_id fallback for issue number extraction.

Problem: In batch mode, the coordinator creates /tmp/implement_pipeline_state.json
but sometimes omits the ``issue_number`` field (the implement-fix.md template
doesn't include it). Completions are recorded under the ACTUAL issue number
(from PIPELINE_ISSUE_NUMBER env var set by coordinator), but the ordering gate
looks up completions under issue 0 — finding nothing — and blocks reviewer/doc-master.

Fix: ``_get_current_issue_number()`` now parses ``run_id`` (pattern:
``issue-{N}-YYYYMMDD-HHMMSS``) as a third fallback when ``issue_number`` is missing.
"""

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "hooks"
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"

sys.path.insert(0, str(HOOKS_DIR))
sys.path.insert(0, str(LIB_DIR))


def _load_get_current_issue_number():
    """Import _get_current_issue_number from unified_pre_tool."""
    import importlib
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "unified_pre_tool",
        HOOKS_DIR / "unified_pre_tool.py",
    )
    module = importlib.util.module_from_spec(spec)

    with mock.patch("sys.stdin", new_callable=lambda: __import__("io").StringIO):
        try:
            spec.loader.exec_module(module)
        except (SystemExit, Exception):
            pass

    return module._get_current_issue_number


class TestIssue869RunIdFallback:
    """Regression tests for run_id-based issue number extraction."""

    def test_run_id_fallback_when_issue_number_missing(self, tmp_path, monkeypatch):
        """When issue_number is absent but run_id has issue pattern, extract from run_id."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(
            json.dumps({
                "mode": "fix",
                "step": 5,
                "run_id": "issue-851-20260415-054107",
            })
        )
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        fn = _load_get_current_issue_number()
        assert fn() == 851

    def test_issue_number_field_takes_precedence_over_run_id(self, tmp_path, monkeypatch):
        """When issue_number IS present, run_id fallback is not used."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(
            json.dumps({
                "issue_number": 999,
                "run_id": "issue-851-20260415-054107",
            })
        )
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        fn = _load_get_current_issue_number()
        assert fn() == 999

    def test_returns_zero_when_neither_issue_number_nor_run_id(self, tmp_path, monkeypatch):
        """When neither issue_number nor valid run_id exists, returns 0."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(
            json.dumps({
                "mode": "fix",
                "step": 5,
            })
        )
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        fn = _load_get_current_issue_number()
        assert fn() == 0

    def test_malformed_run_id_no_issue_prefix(self, tmp_path, monkeypatch):
        """run_id without 'issue-' prefix is ignored gracefully."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(
            json.dumps({
                "mode": "full",
                "run_id": "batch-20260415-064838",
            })
        )
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        fn = _load_get_current_issue_number()
        assert fn() == 0

    def test_malformed_run_id_no_digits_after_issue(self, tmp_path, monkeypatch):
        """run_id with 'issue-' but no digits returns 0."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(
            json.dumps({
                "mode": "fix",
                "run_id": "issue-abc-20260415",
            })
        )
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        fn = _load_get_current_issue_number()
        assert fn() == 0

    def test_run_id_non_string_type_handled(self, tmp_path, monkeypatch):
        """Non-string run_id (e.g., int) is handled gracefully."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(
            json.dumps({
                "mode": "fix",
                "run_id": 12345,
            })
        )
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        fn = _load_get_current_issue_number()
        assert fn() == 0

    def test_run_id_with_large_issue_number(self, tmp_path, monkeypatch):
        """Large issue numbers in run_id are extracted correctly."""
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text(
            json.dumps({
                "run_id": "issue-12345-20260415-120000",
            })
        )
        monkeypatch.setenv("PIPELINE_STATE_FILE", str(state_file))
        monkeypatch.delenv("PIPELINE_ISSUE_NUMBER", raising=False)

        fn = _load_get_current_issue_number()
        assert fn() == 12345
