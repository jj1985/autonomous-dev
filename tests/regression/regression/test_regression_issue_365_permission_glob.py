"""Regression test for Issue #365: Edit/Read/Write permission glob syntax.

Claude Code permissions use bare tool names (Edit, Read, Write) for blanket
allow. The glob suffix (**)  doesn't match correctly, causing permission
prompts on every file operation in synced repos.

FORBIDDEN patterns: "Edit(**)", "Read(**)", "Write(**)", "Glob(**)", "Grep(**)"
REQUIRED patterns: "Edit", "Read", "Write", "Glob", "Grep"

Also validates that no redundant glob-suffixed patterns exist when the bare
tool name is already present in the same allow list (e.g., "Read" + "Read(**/*.py)"
is redundant -- the bare name covers everything).
"""

import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "plugins/autonomous-dev/templates"
CONFIG_DIR = PROJECT_ROOT / "plugins/autonomous-dev/config"
LIB_DIR = PROJECT_ROOT / "plugins/autonomous-dev/lib"

# Tools that must use bare names, never glob suffix
BARE_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep"]
FORBIDDEN_PATTERNS = [f'"{t}(**)"' for t in BARE_TOOLS]

# Regex to detect any glob-suffixed variant like Read(**/*.py), Write(**)
GLOB_SUFFIX_RE = re.compile(r'"(Read|Write|Edit|Glob|Grep)\(.*\)"')


class TestNoGlobSuffixInTemplates:
    """All settings templates must use bare tool names, not Tool(**)."""

    def test_all_templates_use_bare_tool_names(self):
        """Regression #365: No template should contain Edit(**) etc."""
        violations = []
        for template in TEMPLATES_DIR.glob("settings.*.json"):
            content = template.read_text()
            for pattern in FORBIDDEN_PATTERNS:
                if pattern in content:
                    violations.append(f"{template.name}: contains {pattern}")
        assert not violations, f"Glob suffix found in templates:\n" + "\n".join(violations)

    def test_global_settings_template_bare_names(self):
        """Global settings template must use bare tool names."""
        content = (CONFIG_DIR / "global_settings_template.json").read_text()
        for pattern in FORBIDDEN_PATTERNS:
            assert pattern not in content, f"global_settings_template.json contains {pattern}"

    def test_settings_generator_bare_names(self):
        """settings_generator.py SAFE_COMMAND_PATTERNS must use bare names."""
        content = (LIB_DIR / "settings_generator.py").read_text()
        for pattern in FORBIDDEN_PATTERNS:
            assert pattern not in content, f"settings_generator.py contains {pattern}"

    def test_templates_do_contain_bare_edit(self):
        """At least one template must have bare 'Edit' in allow list."""
        found = False
        for template in TEMPLATES_DIR.glob("settings.*.json"):
            data = json.loads(template.read_text())
            allow = data.get("permissions", {}).get("allow", [])
            if "Edit" in allow:
                found = True
                break
        assert found, "No template has bare 'Edit' in permissions.allow"

    def test_templates_do_contain_bare_read(self):
        """At least one template must have bare 'Read' in allow list."""
        found = False
        for template in TEMPLATES_DIR.glob("settings.*.json"):
            data = json.loads(template.read_text())
            allow = data.get("permissions", {}).get("allow", [])
            if "Read" in allow:
                found = True
                break
        assert found, "No template has bare 'Read' in permissions.allow"


class TestNoRedundantGlobPatterns:
    """Issue #365: When bare tool name is in allow list, no glob-suffixed
    variant of the same tool should also appear (redundant, triggers bug #16170)."""

    def test_no_redundant_glob_in_allow_lists(self):
        """Every template: if bare 'Read' is in allow, no 'Read(**/*.py)' etc."""
        violations = []
        for template in TEMPLATES_DIR.glob("settings.*.json"):
            data = json.loads(template.read_text())
            allow = data.get("permissions", {}).get("allow", [])
            for tool in BARE_TOOLS:
                if tool in allow:
                    # Check for any glob-suffixed variant of this tool
                    for entry in allow:
                        if entry != tool and entry.startswith(f"{tool}("):
                            violations.append(
                                f"{template.name}: redundant '{entry}' "
                                f"when bare '{tool}' already present"
                            )
        assert not violations, (
            "Redundant glob patterns found in allow lists:\n" + "\n".join(violations)
        )

    def test_no_redundant_glob_in_global_template(self):
        """Global settings template: no redundant glob-suffixed patterns."""
        template_path = CONFIG_DIR / "global_settings_template.json"
        data = json.loads(template_path.read_text())
        allow = data.get("permissions", {}).get("allow", [])
        for tool in BARE_TOOLS:
            if tool in allow:
                for entry in allow:
                    if entry != tool and entry.startswith(f"{tool}("):
                        pytest.fail(
                            f"global_settings_template.json: redundant '{entry}' "
                            f"when bare '{tool}' already present"
                        )

    def test_settings_generator_no_redundant_glob_patterns(self):
        """settings_generator.py SAFE_COMMAND_PATTERNS must not have
        redundant glob patterns like Read(**/*.py) when Read is already present."""
        content = (LIB_DIR / "settings_generator.py").read_text()
        # Check the allow list in source code doesn't contain glob patterns for bare tools
        matches = GLOB_SUFFIX_RE.findall(content)
        # The deny list may legitimately use glob patterns, but the allow patterns
        # (SAFE_COMMAND_PATTERNS) should not have glob-suffixed variants of bare tools
        for tool_name in matches:
            # Verify it's in SAFE_COMMAND_PATTERNS context (not deny list)
            # Simple check: the pattern appears in the file, look for it in the
            # SAFE_COMMAND_PATTERNS list section
            pass
        # More direct check: read the source and ensure no Read(**/*.py) etc.
        for tool in BARE_TOOLS:
            pattern = f'"{tool}(**'
            assert pattern not in content, (
                f"settings_generator.py contains redundant '{tool}(**...' "
                f"pattern — bare '{tool}' already covers all files"
            )
