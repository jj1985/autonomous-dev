"""
Regression tests for Issue #671: Research skip bypass not in known patterns.

Bug: In batch sessions, both researcher-local and researcher agents are skipped
for ALL issues using "pre-researched content in issue body" justification. This
exemption was not registered in known_bypass_patterns.json, so the CIA agent
could not detect it as a batch-wide bypass pattern.

Evidence: batch-20260406-025344 -- 6/6 issues all skipped researchers.

Fix: Added research_skip_entire_batch pattern to known_bypass_patterns.json with
severity=warning and a constraint explaining when the skip is legitimate (per-issue
with fresh /create-issue cache) vs concerning (entire batch).

These tests verify the pattern exists and would break if removed.
"""

import json
from pathlib import Path

import pytest

# Portable project root detection
_current = Path.cwd()
while _current != _current.parent:
    if (_current / ".git").exists() or (_current / ".claude").exists():
        PROJECT_ROOT = _current
        break
    _current = _current.parent
else:
    PROJECT_ROOT = Path.cwd()

PLUGIN_DIR = PROJECT_ROOT / "plugins" / "autonomous-dev"
INSTALLED_CONFIG = PROJECT_ROOT / ".claude" / "config"


class TestIssue671ResearchSkipBypassPattern:
    """Regression: research_skip_entire_batch pattern must exist in bypass registry."""

    @pytest.fixture
    def plugin_config(self) -> dict:
        """Load bypass patterns from plugin source config."""
        path = PLUGIN_DIR / "config" / "known_bypass_patterns.json"
        return json.loads(path.read_text())

    @pytest.fixture
    def installed_config(self) -> dict:
        """Load bypass patterns from installed config."""
        path = INSTALLED_CONFIG / "known_bypass_patterns.json"
        return json.loads(path.read_text())

    def _find_pattern(self, config: dict, pattern_id: str) -> dict | None:
        """Find a pattern by id in the config."""
        for p in config["patterns"]:
            if p["id"] == pattern_id:
                return p
        return None

    def test_pattern_exists_in_plugin_config(self, plugin_config: dict) -> None:
        """research_skip_entire_batch must exist in plugin bypass patterns."""
        pattern = self._find_pattern(plugin_config, "research_skip_entire_batch")
        assert pattern is not None, (
            "Regression #671: research_skip_entire_batch pattern missing from "
            "plugins/autonomous-dev/config/known_bypass_patterns.json"
        )

    def test_pattern_exists_in_installed_config(self, installed_config: dict) -> None:
        """research_skip_entire_batch must exist in installed bypass patterns."""
        pattern = self._find_pattern(installed_config, "research_skip_entire_batch")
        assert pattern is not None, (
            "Regression #671: research_skip_entire_batch pattern missing from "
            ".claude/config/known_bypass_patterns.json"
        )

    def test_pattern_severity_is_warning(self, plugin_config: dict) -> None:
        """Pattern severity must be warning, not critical.

        Research skip is a legitimate exemption for individual issues with
        fresh /create-issue cache. It only becomes concerning when applied
        to ALL issues in a batch.
        """
        pattern = self._find_pattern(plugin_config, "research_skip_entire_batch")
        assert pattern is not None
        assert pattern["severity"] == "warning", (
            f"Regression #671: severity must be 'warning' (not '{pattern['severity']}'). "
            "Research skip is legitimate per-issue; only flag when batch-wide."
        )

    def test_pattern_has_constraint_field(self, plugin_config: dict) -> None:
        """Pattern must have constraint field explaining when skip is valid."""
        pattern = self._find_pattern(plugin_config, "research_skip_entire_batch")
        assert pattern is not None
        assert "constraint" in pattern, (
            "Regression #671: pattern must have 'constraint' field explaining "
            "when research skip is legitimate vs concerning"
        )
        assert len(pattern["constraint"]) > 0, (
            "Regression #671: constraint field must not be empty"
        )

    def test_pattern_references_issue_671(self, plugin_config: dict) -> None:
        """Pattern must reference issue #671."""
        pattern = self._find_pattern(plugin_config, "research_skip_entire_batch")
        assert pattern is not None
        assert pattern.get("issue") == "#671", (
            f"Regression #671: pattern must reference '#671', got '{pattern.get('issue')}'"
        )

    def test_pattern_has_batch_pattern_detection_type(self, plugin_config: dict) -> None:
        """Detection type must be batch_pattern to distinguish from per-issue checks."""
        pattern = self._find_pattern(plugin_config, "research_skip_entire_batch")
        assert pattern is not None
        assert pattern["detection"]["type"] == "batch_pattern", (
            "Regression #671: detection type must be 'batch_pattern'"
        )

    def test_pattern_has_detection_indicators(self, plugin_config: dict) -> None:
        """Pattern must have meaningful detection indicators."""
        pattern = self._find_pattern(plugin_config, "research_skip_entire_batch")
        assert pattern is not None
        indicators = pattern["detection"]["indicators"]
        assert len(indicators) >= 3, (
            f"Regression #671: need at least 3 detection indicators, got {len(indicators)}"
        )

    def test_configs_in_sync(self, plugin_config: dict, installed_config: dict) -> None:
        """Plugin and installed bypass patterns must contain the same pattern."""
        plugin_pattern = self._find_pattern(plugin_config, "research_skip_entire_batch")
        installed_pattern = self._find_pattern(installed_config, "research_skip_entire_batch")
        assert plugin_pattern is not None
        assert installed_pattern is not None
        assert plugin_pattern == installed_pattern, (
            "Regression #671: research_skip_entire_batch pattern must be identical "
            "in both plugin and installed config"
        )

    def test_pattern_references_hard_gate(self, plugin_config: dict) -> None:
        """Pattern must reference the STEP 4 hard gate."""
        pattern = self._find_pattern(plugin_config, "research_skip_entire_batch")
        assert pattern is not None
        assert "STEP 4" in pattern.get("hard_gate", ""), (
            "Regression #671: hard_gate must reference STEP 4 research agents"
        )
