"""Unit tests for dependabot_tracker.py (Issue #767).

All subprocess.run calls are mocked. No real GitHub API calls are made.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "plugins" / "autonomous-dev" / "lib"))

from dependabot_tracker import (
    _gh,
    _maybe_create_medium_batch,
    _validate_ghsa_id,
    create_individual_issue,
    get_open_alerts,
    issue_exists_for_ghsa,
    parse_owner_repo,
    run_dependabot_tracker,
)


# ---------------------------------------------------------------------------
# Helpers: common alert fixtures
# ---------------------------------------------------------------------------

def _make_alert(
    ghsa_id: str = "GHSA-abcd-efgh-ijkl",
    severity: str = "high",
    package: str = "lodash",
    summary: str = "Prototype pollution",
    cve_id: str = "CVE-2021-12345",
) -> dict:
    """Build a realistic Dependabot alert dict."""
    return {
        "security_advisory": {
            "ghsa_id": ghsa_id,
            "severity": severity,
            "summary": summary,
            "cve_id": cve_id,
        },
        "security_vulnerability": {
            "package": {"name": package},
        },
        "html_url": f"https://github.com/owner/repo/security/dependabot/1",
    }


# ---------------------------------------------------------------------------
# URL parsing tests
# ---------------------------------------------------------------------------

class TestParseOwnerRepo:
    def test_ssh_format(self):
        result = parse_owner_repo("git@github.com:myorg/myrepo.git")
        assert result == ("myorg", "myrepo")

    def test_https_format(self):
        result = parse_owner_repo("https://github.com/myorg/myrepo.git")
        assert result == ("myorg", "myrepo")

    def test_https_without_git_suffix(self):
        result = parse_owner_repo("https://github.com/myorg/myrepo")
        assert result == ("myorg", "myrepo")

    def test_invalid_url_returns_none(self):
        result = parse_owner_repo("https://gitlab.com/myorg/myrepo.git")
        assert result is None

    def test_non_github_remote_returns_none(self):
        result = parse_owner_repo("git@bitbucket.org:myorg/myrepo.git")
        assert result is None


# ---------------------------------------------------------------------------
# GHSA ID validation tests
# ---------------------------------------------------------------------------

class TestValidateGhsaId:
    def test_valid_lowercase(self):
        assert _validate_ghsa_id("GHSA-abcd-ef12-3456") is True

    def test_uppercase_letters_rejected(self):
        assert _validate_ghsa_id("GHSA-ABCD-EFGH-IJKL") is False

    def test_wrong_segment_count(self):
        assert _validate_ghsa_id("GHSA-abcd-efgh") is False

    def test_empty_string(self):
        assert _validate_ghsa_id("") is False

    def test_none_value(self):
        assert _validate_ghsa_id(None) is False

    def test_too_long_segments(self):
        assert _validate_ghsa_id("GHSA-abcde-efgh-ijkl") is False


# ---------------------------------------------------------------------------
# _gh helper tests
# ---------------------------------------------------------------------------

class TestGhHelper:
    @patch("dependabot_tracker.subprocess.run")
    def test_success_returns_parsed_json(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout='[{"id": 1}]', stderr=""
        )
        result = _gh(["api", "/repos/o/r/dependabot/alerts"])
        assert result == [{"id": 1}]
        mock_run.assert_called_once()
        # Verify shell=False
        _, kwargs = mock_run.call_args
        assert kwargs.get("shell") is False

    @patch("dependabot_tracker.subprocess.run")
    def test_nonzero_return_code_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        assert _gh(["api", "/foo"]) is None

    @patch("dependabot_tracker.subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 30))
    def test_timeout_returns_none(self, mock_run):
        assert _gh(["api", "/foo"], timeout=5) is None

    @patch("dependabot_tracker.subprocess.run", side_effect=FileNotFoundError)
    def test_gh_not_installed_returns_none(self, mock_run):
        assert _gh(["api", "/foo"]) is None


# ---------------------------------------------------------------------------
# Alert fetching tests
# ---------------------------------------------------------------------------

class TestGetOpenAlerts:
    @patch("dependabot_tracker._gh")
    def test_success_returns_list(self, mock_gh):
        alerts = [_make_alert()]
        mock_gh.return_value = alerts
        result = get_open_alerts("owner", "repo")
        assert result == alerts

    @patch("dependabot_tracker._gh", return_value=None)
    def test_api_error_returns_empty(self, mock_gh):
        assert get_open_alerts("owner", "repo") == []

    @patch("dependabot_tracker._gh", side_effect=Exception("timeout"))
    def test_exception_returns_empty(self, mock_gh):
        assert get_open_alerts("owner", "repo") == []


# ---------------------------------------------------------------------------
# Issue deduplication tests
# ---------------------------------------------------------------------------

class TestIssueExistsForGhsa:
    @patch("dependabot_tracker._gh")
    def test_found_via_html_comment(self, mock_gh):
        mock_gh.return_value = [
            {"body": "<!-- GHSA: GHSA-abcd-efgh-ijkl --> some text"}
        ]
        assert issue_exists_for_ghsa("o", "r", "GHSA-abcd-efgh-ijkl") is True

    @patch("dependabot_tracker._gh")
    def test_not_found(self, mock_gh):
        mock_gh.return_value = [{"body": "no marker here"}]
        assert issue_exists_for_ghsa("o", "r", "GHSA-abcd-efgh-ijkl") is False

    @patch("dependabot_tracker._gh", return_value=None)
    def test_api_error_returns_false(self, mock_gh):
        assert issue_exists_for_ghsa("o", "r", "GHSA-abcd-efgh-ijkl") is False

    def test_invalid_ghsa_returns_false(self):
        assert issue_exists_for_ghsa("o", "r", "INVALID") is False


# ---------------------------------------------------------------------------
# Issue creation tests
# ---------------------------------------------------------------------------

class TestCreateIndividualIssue:
    @patch("dependabot_tracker._gh")
    def test_correct_title_format(self, mock_gh):
        mock_gh.return_value = {"url": "https://github.com/o/r/issues/1"}
        alert = _make_alert(ghsa_id="GHSA-abcd-efgh-ijkl", severity="high", package="lodash")
        result = create_individual_issue("o", "r", alert)
        assert result is True
        args = mock_gh.call_args[0][0]
        # Find --title argument
        title_idx = args.index("--title") + 1
        assert args[title_idx] == "security(lodash): GHSA-abcd-efgh-ijkl [high]"

    @patch("dependabot_tracker._gh")
    def test_body_contains_html_comment(self, mock_gh):
        mock_gh.return_value = {"url": "https://github.com/o/r/issues/1"}
        alert = _make_alert(ghsa_id="GHSA-abcd-efgh-ijkl")
        create_individual_issue("o", "r", alert)
        args = mock_gh.call_args[0][0]
        body_idx = args.index("--body") + 1
        assert "<!-- GHSA: GHSA-abcd-efgh-ijkl -->" in args[body_idx]

    @patch("dependabot_tracker._gh")
    def test_labels_include_security(self, mock_gh):
        mock_gh.return_value = {"url": "ok"}
        alert = _make_alert()
        create_individual_issue("o", "r", alert)
        args = mock_gh.call_args[0][0]
        assert "security" in args
        assert "dependabot" in args

    def test_invalid_ghsa_returns_false(self):
        alert = _make_alert(ghsa_id="INVALID-ID")
        assert create_individual_issue("o", "r", alert) is False


# ---------------------------------------------------------------------------
# Medium batch tests
# ---------------------------------------------------------------------------

class TestMaybeCreateMediumBatch:
    @patch("dependabot_tracker._gh")
    def test_creates_new_batch(self, mock_gh):
        # First call: search returns no existing batch; second call: create succeeds
        mock_gh.side_effect = [
            [],  # no existing batch
            {"url": "https://github.com/o/r/issues/2"},  # create
        ]
        alerts = [_make_alert(severity="medium", ghsa_id="GHSA-aaaa-bbbb-cccc")]
        assert _maybe_create_medium_batch("o", "r", alerts) is True

    @patch("dependabot_tracker._gh")
    def test_skips_when_batch_exists(self, mock_gh):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        yr, wk, _ = now.isocalendar()
        marker = f"<!-- GHSA-BATCH: {yr}-W{wk:02d} -->"
        mock_gh.return_value = [{"body": marker}]
        alerts = [_make_alert(severity="medium")]
        assert _maybe_create_medium_batch("o", "r", alerts) is False

    def test_empty_alerts_returns_false(self):
        assert _maybe_create_medium_batch("o", "r", []) is False


# ---------------------------------------------------------------------------
# Entry point tests
# ---------------------------------------------------------------------------

class TestRunDependabotTracker:
    @patch("dependabot_tracker.create_individual_issue", return_value=True)
    @patch("dependabot_tracker.issue_exists_for_ghsa", return_value=False)
    @patch("dependabot_tracker._maybe_create_medium_batch", return_value=True)
    @patch("dependabot_tracker.get_open_alerts")
    def test_mixed_severities(self, mock_alerts, mock_batch, mock_exists, mock_create):
        mock_alerts.return_value = [
            _make_alert(severity="critical", ghsa_id="GHSA-aaaa-bbbb-cccc"),
            _make_alert(severity="medium", ghsa_id="GHSA-dddd-eeee-ffff"),
            _make_alert(severity="low", ghsa_id="GHSA-gggg-hhhh-iiii"),
        ]
        result = run_dependabot_tracker("o", "r")
        assert result["created"] >= 1  # at least the critical one
        assert result["skipped"] >= 1  # the low one

    @patch("dependabot_tracker.issue_exists_for_ghsa", return_value=True)
    @patch("dependabot_tracker.get_open_alerts")
    def test_all_duplicates_zero_created(self, mock_alerts, mock_exists):
        mock_alerts.return_value = [
            _make_alert(severity="high", ghsa_id="GHSA-aaaa-bbbb-cccc"),
        ]
        result = run_dependabot_tracker("o", "r")
        assert result["created"] == 0
        assert result["skipped"] >= 1

    @patch("dependabot_tracker.get_open_alerts", side_effect=Exception("API down"))
    def test_api_failure_returns_error_dict(self, mock_alerts):
        result = run_dependabot_tracker("o", "r")
        assert isinstance(result, dict)
        assert result["errors"] >= 1

    @patch("dependabot_tracker.get_open_alerts", return_value=[])
    def test_no_alerts_returns_zero_counts(self, mock_alerts):
        result = run_dependabot_tracker("o", "r")
        assert result == {"created": 0, "skipped": 0, "errors": 0}


# ---------------------------------------------------------------------------
# Security invariant: no shell=True in source
# ---------------------------------------------------------------------------

class TestSecurityInvariant:
    def test_source_has_no_shell_true(self):
        """Read dependabot_tracker.py source and verify shell=True is absent."""
        src = (
            REPO_ROOT / "plugins" / "autonomous-dev" / "lib" / "dependabot_tracker.py"
        )
        content = src.read_text()
        assert "shell=True" not in content, "dependabot_tracker.py MUST NOT use shell=True"
