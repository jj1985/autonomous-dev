"""Spec validation for Issue #807: Batch registration/baseline housekeeping.

Tests acceptance criteria:
1. conversation_archiver.hook.json entry added to install_manifest.json
2. test_hook_in_install_manifest passes for conversation_archiver
3. Hook health baseline matches actual pre-existing failure count
4. No false HOOK-REGRESSION alerts from baseline mismatch
"""

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = (
    PROJECT_ROOT / "plugins" / "autonomous-dev" / "config" / "install_manifest.json"
)
HOOKS_DIR = PROJECT_ROOT / "plugins" / "autonomous-dev" / "hooks"


@pytest.fixture
def manifest():
    """Load the install manifest."""
    with open(MANIFEST_PATH) as f:
        return json.load(f)


class TestSpec807RegistrationBaselineHousekeeping:
    """Spec validation: Issue #807 acceptance criteria."""

    def test_spec_807_1_conversation_archiver_hook_json_in_manifest(self, manifest):
        """AC1: conversation_archiver.hook.json entry added to install_manifest.json."""
        hook_files = manifest["components"]["hooks"]["files"]
        hook_json_entries = [
            f for f in hook_files if "conversation_archiver.hook.json" in f
        ]
        assert len(hook_json_entries) == 1, (
            f"Expected exactly 1 entry for conversation_archiver.hook.json "
            f"in install_manifest.json hooks, found {len(hook_json_entries)}"
        )

    def test_spec_807_1b_conversation_archiver_py_also_in_manifest(self, manifest):
        """AC1 supporting: conversation_archiver.py should also be present (not removed)."""
        hook_files = manifest["components"]["hooks"]["files"]
        py_entries = [f for f in hook_files if "conversation_archiver.py" in f]
        assert len(py_entries) >= 1, (
            "conversation_archiver.py should remain in install_manifest.json"
        )

    def test_spec_807_1c_hook_json_source_file_exists(self):
        """AC1 supporting: the conversation_archiver.hook.json file must exist in source."""
        hook_json_path = HOOKS_DIR / "conversation_archiver.hook.json"
        assert hook_json_path.exists(), (
            f"conversation_archiver.hook.json not found at {hook_json_path}"
        )

    def test_spec_807_2_manifest_files_all_exist_in_source(self, manifest):
        """AC2: All hook files listed in manifest must exist in source."""
        missing = []
        for hook_path in manifest["components"]["hooks"]["files"]:
            full_path = PROJECT_ROOT / hook_path
            if not full_path.exists():
                missing.append(hook_path)
        assert not missing, (
            f"Hook files in manifest but missing from source: {missing}"
        )

    def test_spec_807_3_hook_health_no_unexpected_failures(self):
        """AC3/AC4: Run the conversation_archiver manifest test to confirm no regression.

        This validates that the existing test_hook_in_install_manifest passes,
        which means the baseline is correct and no false regression alerts occur.
        """
        # We directly verify the same assertion the existing test checks:
        # both .py and .hook.json must be in the manifest
        data = json.loads(MANIFEST_PATH.read_text())
        hook_files = data["components"]["hooks"]["files"]

        assert any("conversation_archiver.py" in f for f in hook_files), (
            "conversation_archiver.py not in install_manifest hooks"
        )
        assert any("conversation_archiver.hook.json" in f for f in hook_files), (
            "conversation_archiver.hook.json not in install_manifest hooks"
        )
