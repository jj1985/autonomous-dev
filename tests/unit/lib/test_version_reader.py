"""Tests for version_reader module."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import with path manipulation matching the project pattern
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "plugins" / "autonomous-dev" / "lib"))

from version_reader import (
    _find_plugin_json,
    _get_git_sha,
    _read_version,
    get_plugin_version,
    reset_cache,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset the module-level cache before each test."""
    reset_cache()
    yield
    reset_cache()


class TestGetPluginVersion:
    """Tests for the main get_plugin_version() function."""

    @patch("version_reader._read_version", return_value="3.50.0")
    @patch("version_reader._get_git_sha", return_value="abc1234")
    def test_full_format_with_sha(self, mock_sha, mock_ver):
        assert get_plugin_version() == "3.50.0 (abc1234)"

    @patch("version_reader._read_version", return_value="3.50.0")
    @patch("version_reader._get_git_sha", return_value=None)
    def test_version_only_when_git_unavailable(self, mock_sha, mock_ver):
        assert get_plugin_version() == "3.50.0"

    @patch("version_reader._read_version", return_value=None)
    def test_unknown_when_version_missing(self, mock_ver):
        assert get_plugin_version() == "unknown"

    @patch("version_reader._read_version", return_value="1.0.0")
    @patch("version_reader._get_git_sha", return_value="def5678")
    def test_caching_returns_same_value(self, mock_sha, mock_ver):
        first = get_plugin_version()
        second = get_plugin_version()
        assert first == second == "1.0.0 (def5678)"
        # _read_version called only once due to caching
        mock_ver.assert_called_once()


class TestFindPluginJson:
    """Tests for _find_plugin_json() discovery."""

    def test_finds_relative_to_file(self):
        # The real plugin.json should be discoverable from lib/
        result = _find_plugin_json()
        assert result is not None
        assert result.name == "plugin.json"

    def test_returns_none_when_no_candidates_exist(self, tmp_path):
        """When no candidate paths contain plugin.json, returns None."""
        # Point __file__ resolution to a directory with no plugin.json
        fake_lib = tmp_path / "plugins" / "autonomous-dev" / "lib"
        fake_lib.mkdir(parents=True)
        fake_file = fake_lib / "version_reader.py"
        fake_file.write_text("", encoding="utf-8")

        with (
            patch("version_reader.__file__", str(fake_file)),
            patch("version_reader.Path.cwd", return_value=tmp_path / "nonexistent"),
            patch("version_reader.Path.home", return_value=tmp_path / "nonexistent"),
        ):
            result = _find_plugin_json()
            assert result is None


class TestReadVersion:
    """Tests for _read_version() JSON parsing."""

    def test_reads_real_plugin_json(self):
        version = _read_version()
        # Real plugin.json should have a version
        assert version is not None
        # Version should look like semver
        parts = version.split(".")
        assert len(parts) >= 2

    @patch("version_reader._find_plugin_json", return_value=None)
    def test_returns_none_when_no_file(self, mock_find):
        assert _read_version() is None

    def test_returns_none_for_corrupted_json(self, tmp_path):
        bad_file = tmp_path / "plugin.json"
        bad_file.write_text("not valid json {{{", encoding="utf-8")

        with patch("version_reader._find_plugin_json", return_value=bad_file):
            assert _read_version() is None

    def test_returns_none_for_missing_version_key(self, tmp_path):
        no_version = tmp_path / "plugin.json"
        no_version.write_text(json.dumps({"name": "test"}), encoding="utf-8")

        with patch("version_reader._find_plugin_json", return_value=no_version):
            assert _read_version() is None

    def test_returns_none_for_empty_version(self, tmp_path):
        empty_ver = tmp_path / "plugin.json"
        empty_ver.write_text(json.dumps({"version": "  "}), encoding="utf-8")

        with patch("version_reader._find_plugin_json", return_value=empty_ver):
            assert _read_version() is None


class TestGetGitSha:
    """Tests for _get_git_sha() subprocess call."""

    def test_returns_sha_in_git_repo(self):
        sha = _get_git_sha()
        # We are in a git repo, so this should return something
        assert sha is not None
        assert len(sha) >= 7

    @patch("version_reader.subprocess.run")
    def test_returns_none_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=2)
        assert _get_git_sha() is None

    @patch("version_reader.subprocess.run")
    def test_returns_none_when_git_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("git not found")
        assert _get_git_sha() is None

    @patch("version_reader.subprocess.run")
    def test_returns_none_on_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        assert _get_git_sha() is None
