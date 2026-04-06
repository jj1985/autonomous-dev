"""Regression test for permission deny rule glob syntax validation.

Incident: A deny rule like "Bash(*$(rm*)" has mismatched parentheses because
$( introduces a subshell but the glob parser treats ( as a grouping operator
needing a matching ). Claude Code skips the ENTIRE settings file when it
encounters invalid glob syntax, silently disabling all hooks and permissions.

This test ensures all deny rules in settings files have valid glob syntax,
specifically balanced parentheses.
"""

import json
from pathlib import Path
from typing import List, Tuple

import pytest


def _extract_deny_rules(settings_path: Path) -> List[str]:
    """Extract all deny rules from a settings JSON file.

    Args:
        settings_path: Path to the settings JSON file

    Returns:
        List of deny rule strings
    """
    data = json.loads(settings_path.read_text())
    permissions = data.get("permissions", {})
    return permissions.get("deny", [])


def _check_balanced_parentheses(rule: str) -> bool:
    """Check if a deny rule has balanced parentheses.

    Counts raw ( and ) characters in the rule string.
    A valid glob pattern must have equal counts.

    Args:
        rule: The deny rule string (e.g. "Bash(rm:-rf*)")

    Returns:
        True if parentheses are balanced, False otherwise
    """
    return rule.count("(") == rule.count(")")


def _check_inner_pattern_balanced(rule: str) -> bool:
    """Check if the pattern inside the outer Tool(...) wrapper has balanced parens.

    For a rule like "Bash(some*pattern)", extracts "some*pattern" and checks
    that any parentheses within it are balanced.

    Args:
        rule: The deny rule string

    Returns:
        True if inner pattern has balanced parentheses, False otherwise
    """
    # Find the first ( and last ) which form the Tool(...) wrapper
    first_open = rule.find("(")
    last_close = rule.rfind(")")

    if first_open == -1 or last_close == -1 or first_open >= last_close:
        # No wrapper pattern found -- treat as valid (other tests catch format issues)
        return True

    inner = rule[first_open + 1 : last_close]
    return inner.count("(") == inner.count(")")


def _find_unbalanced_rules(rules: List[str]) -> List[Tuple[str, str]]:
    """Find all deny rules with unbalanced parentheses.

    Args:
        rules: List of deny rule strings

    Returns:
        List of (rule, reason) tuples for rules that failed validation
    """
    failures = []
    for rule in rules:
        if not _check_balanced_parentheses(rule):
            open_count = rule.count("(")
            close_count = rule.count(")")
            failures.append(
                (rule, f"unbalanced parens: {open_count} open, {close_count} close")
            )
        elif not _check_inner_pattern_balanced(rule):
            first_open = rule.find("(")
            last_close = rule.rfind(")")
            inner = rule[first_open + 1 : last_close]
            failures.append(
                (
                    rule,
                    f"inner pattern has unbalanced parens: "
                    f"{inner.count('(')} open, {inner.count(')')} close",
                )
            )
    return failures


class TestPermissionGlobSyntax:
    """Validate glob syntax in permission deny rules across settings files.

    Claude Code's glob parser requires balanced parentheses. A single
    mismatched paren causes the entire settings file to be skipped,
    silently disabling all hooks and permissions.
    """

    SETTINGS_FILES = {
        "template": "plugins/autonomous-dev/templates/settings.default.json",
        "installed": ".claude/settings.json",
    }

    def test_deny_rules_have_balanced_parentheses(self, project_root: Path) -> None:
        """All deny rules in all settings files must have balanced parentheses."""
        all_failures: List[str] = []

        for label, rel_path in self.SETTINGS_FILES.items():
            settings_path = project_root / rel_path
            if not settings_path.exists():
                continue

            rules = _extract_deny_rules(settings_path)
            failures = _find_unbalanced_rules(rules)

            for rule, reason in failures:
                all_failures.append(f"  [{label}] {rule!r} -- {reason}")

        if all_failures:
            pytest.fail(
                f"Deny rules with invalid glob syntax ({len(all_failures)}):\n"
                + "\n".join(all_failures)
                + "\n\nClaude Code skips the ENTIRE settings file on invalid glob syntax, "
                "silently disabling all hooks and permissions."
            )

    def test_settings_default_template_deny_rules(self, project_root: Path) -> None:
        """All deny rules in the default template must have balanced parentheses."""
        template_path = project_root / self.SETTINGS_FILES["template"]
        if not template_path.exists():
            pytest.skip(f"Template not found: {self.SETTINGS_FILES['template']}")

        rules = _extract_deny_rules(template_path)
        assert len(rules) > 0, "Template has no deny rules -- expected a non-empty deny list"

        failures = _find_unbalanced_rules(rules)
        if failures:
            details = "\n".join(f"  {rule!r} -- {reason}" for rule, reason in failures)
            pytest.fail(
                f"Template deny rules with unbalanced parentheses ({len(failures)}):\n"
                + details
            )

    def test_installed_settings_deny_rules(self, project_root: Path) -> None:
        """All deny rules in .claude/settings.json must have balanced parentheses."""
        installed_path = project_root / self.SETTINGS_FILES["installed"]
        if not installed_path.exists():
            pytest.skip("Installed settings not found: .claude/settings.json")

        rules = _extract_deny_rules(installed_path)
        assert len(rules) > 0, "Installed settings has no deny rules -- expected a non-empty deny list"

        failures = _find_unbalanced_rules(rules)
        if failures:
            details = "\n".join(f"  {rule!r} -- {reason}" for rule, reason in failures)
            pytest.fail(
                f"Installed settings deny rules with unbalanced parentheses ({len(failures)}):\n"
                + details
            )
