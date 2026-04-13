"""Regression test for permission deny rule glob syntax validation.

Incident 1: A deny rule like "Bash(*$(rm*)" has mismatched parentheses because
$( introduces a subshell but the glob parser treats ( as a grouping operator
needing a matching ). Claude Code skips the ENTIRE settings file when it
encounters invalid glob syntax, silently disabling all hooks and permissions.

Incident 2: A deny rule like "Bash(npm:*install*-g*)" is invalid because
Claude Code's Tool(command:pattern) syntax requires :* to be at the END of
the pattern. Content after :* causes the rule to be flagged as invalid and
skipped with: 'Invalid permission rule ... was skipped: The :* pattern must
be at the end.'

This test ensures all deny rules in settings files have valid glob syntax,
specifically balanced parentheses and correct :* placement.
"""

import ast
import json
import re
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


def _check_colon_star_at_end(rule: str) -> bool:
    """Check that :* in a deny rule is only at the end of the pattern.

    Claude Code's Tool(command:pattern) syntax requires that :* appears
    only at the END of the pattern. Having content after :* (e.g.,
    "Bash(npm:*install*-g*)") causes the rule to be skipped as invalid.

    The :* must be followed only by the closing ) or end of string.
    Patterns like "Bash(npm:*)" are valid. Patterns like "Bash(npm:*foo*)"
    are invalid.

    Args:
        rule: The deny rule string

    Returns:
        True if the rule is valid (no content after :*), False otherwise
    """
    # Find all occurrences of :* in the rule
    idx = 0
    while True:
        pos = rule.find(":*", idx)
        if pos == -1:
            break
        # Check what follows :* — only ) or " or end-of-string is valid
        after_pos = pos + 2
        if after_pos < len(rule):
            next_char = rule[after_pos]
            if next_char not in (")", '"'):
                return False
        idx = after_pos
    return True


def _find_colon_star_violations(rules: List[str]) -> List[Tuple[str, str]]:
    """Find deny rules where :* is not at the end of the pattern.

    Args:
        rules: List of deny rule strings

    Returns:
        List of (rule, reason) tuples for rules that have content after :*
    """
    failures = []
    for rule in rules:
        if not _check_colon_star_at_end(rule):
            failures.append(
                (rule, "has content after ':*' — Claude Code requires :* at the end")
            )
    return failures


def _extract_deny_rules_from_python(source_path: Path) -> List[str]:
    """Extract string literals from the DEFAULT_DENY_LIST in settings_generator.py.

    Parses the Python AST to find the DEFAULT_DENY_LIST assignment and
    extracts all string constant elements.

    Args:
        source_path: Path to settings_generator.py

    Returns:
        List of deny rule strings from the Python source
    """
    source = source_path.read_text()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "DEFAULT_DENY_LIST":
                    if isinstance(node.value, ast.List):
                        return [
                            elt.value
                            for elt in node.value.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        ]
    return []


class TestPermissionGlobSyntax:
    """Validate glob syntax in permission deny rules across settings files.

    Claude Code's glob parser requires balanced parentheses. A single
    mismatched paren causes the entire settings file to be skipped,
    silently disabling all hooks and permissions.
    """

    SETTINGS_FILES = {
        "template": "plugins/autonomous-dev/templates/settings.default.json",
        "installed": ".claude/settings.json",
        "global_template": "plugins/autonomous-dev/config/global_settings_template.json",
    }

    GENERATOR_PATH = "plugins/autonomous-dev/lib/settings_generator.py"

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

    # All files to validate for :* placement — including installed settings.
    # The sync script now regenerates deny rules on every deploy, so the
    # installed file should always match the canonical source.
    COLON_STAR_SOURCE_FILES = {
        "template": "plugins/autonomous-dev/templates/settings.default.json",
        "global_template": "plugins/autonomous-dev/config/global_settings_template.json",
        "installed": ".claude/settings.json",
    }

    def test_colon_star_must_be_at_end_in_settings_files(self, project_root: Path) -> None:
        """Deny rules with :* must have it at the end of the pattern.

        Regression test for: 'Invalid permission rule "Bash(npm:*install*-g*)"
        was skipped: The :* pattern must be at the end.'

        Claude Code's Tool(command:pattern) syntax requires :* to terminate
        the pattern. Content after :* causes the rule to be silently skipped.

        Validates source-of-truth template files (not the installed settings,
        which is a generated artifact).
        """
        all_failures: List[str] = []

        for label, rel_path in self.COLON_STAR_SOURCE_FILES.items():
            settings_path = project_root / rel_path
            if not settings_path.exists():
                continue

            rules = _extract_deny_rules(settings_path)
            failures = _find_colon_star_violations(rules)

            for rule, reason in failures:
                all_failures.append(f"  [{label}] {rule!r} -- {reason}")

        if all_failures:
            pytest.fail(
                f"Deny rules with content after ':*' ({len(all_failures)}):\n"
                + "\n".join(all_failures)
                + "\n\nClaude Code requires ':*' to be at the end of the pattern. "
                "Content after ':*' causes the rule to be silently skipped."
            )

    def test_colon_star_must_be_at_end_in_generator(self, project_root: Path) -> None:
        """DEFAULT_DENY_LIST in settings_generator.py must not have content after :*.

        Regression test for the source of truth: the Python deny list that
        generates settings files. If the generator has invalid rules, every
        generated settings file will inherit them.
        """
        generator_path = project_root / self.GENERATOR_PATH
        if not generator_path.exists():
            pytest.skip(f"Generator not found: {self.GENERATOR_PATH}")

        rules = _extract_deny_rules_from_python(generator_path)
        assert len(rules) > 0, (
            "DEFAULT_DENY_LIST not found or empty in settings_generator.py"
        )

        failures = _find_colon_star_violations(rules)
        if failures:
            details = "\n".join(f"  {rule!r} -- {reason}" for rule, reason in failures)
            pytest.fail(
                f"DEFAULT_DENY_LIST rules with content after ':*' ({len(failures)}):\n"
                + details
                + "\n\nFix: ensure ':*' is at the end, e.g., 'Bash(npm:*)' not "
                "'Bash(npm:*install*-g*)'"
            )

    def test_global_settings_template_deny_rules(self, project_root: Path) -> None:
        """All deny rules in global_settings_template.json must have valid syntax.

        Validates both balanced parentheses and :* placement for the global
        settings template used for user-level Claude Code configuration.
        """
        template_path = project_root / self.SETTINGS_FILES["global_template"]
        if not template_path.exists():
            pytest.skip(
                f"Global template not found: {self.SETTINGS_FILES['global_template']}"
            )

        rules = _extract_deny_rules(template_path)
        assert len(rules) > 0, (
            "Global template has no deny rules -- expected a non-empty deny list"
        )

        # Check balanced parens
        paren_failures = _find_unbalanced_rules(rules)
        # Check :* placement
        colon_star_failures = _find_colon_star_violations(rules)

        all_failures = []
        for rule, reason in paren_failures:
            all_failures.append(f"  {rule!r} -- {reason}")
        for rule, reason in colon_star_failures:
            all_failures.append(f"  {rule!r} -- {reason}")

        if all_failures:
            pytest.fail(
                f"Global template deny rules with invalid syntax ({len(all_failures)}):\n"
                + "\n".join(all_failures)
            )
