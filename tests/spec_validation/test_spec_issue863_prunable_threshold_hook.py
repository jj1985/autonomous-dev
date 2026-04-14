"""Spec validation tests for Issue #863: PreCommit prunable threshold hook."""

from __future__ import annotations
import json, sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "hooks"
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
TEMPLATES_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "templates"
CONFIG_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "config"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

def test_spec_prunable_threshold_1_hook_file_exists():
    assert (HOOKS_DIR / "enforce_prunable_threshold.py").exists()

@patch("enforce_prunable_threshold.count_prunable")
@patch("enforce_prunable_threshold.get_project_root")
def test_spec_prunable_threshold_2_blocks_above_threshold(mock_root, mock_count, capsys, monkeypatch):
    monkeypatch.delenv("SKIP_PRUNABLE_GATE", raising=False)
    mock_root.return_value = Path("/fake/project")
    mock_count.return_value = 150
    from enforce_prunable_threshold import main
    result = main()
    assert result == 2
    captured = capsys.readouterr()
    assert len(captured.err) > 0

@patch("enforce_prunable_threshold.count_prunable")
@patch("enforce_prunable_threshold.get_project_root")
def test_spec_prunable_threshold_3a_allows_below_threshold(mock_root, mock_count, monkeypatch):
    monkeypatch.delenv("SKIP_PRUNABLE_GATE", raising=False)
    mock_root.return_value = Path("/fake/project")
    mock_count.return_value = 50
    from enforce_prunable_threshold import main
    assert main() == 0

@patch("enforce_prunable_threshold.count_prunable")
@patch("enforce_prunable_threshold.get_project_root")
def test_spec_prunable_threshold_3b_allows_at_exactly_threshold(mock_root, mock_count, monkeypatch):
    monkeypatch.delenv("SKIP_PRUNABLE_GATE", raising=False)
    mock_root.return_value = Path("/fake/project")
    mock_count.return_value = 100
    from enforce_prunable_threshold import main
    assert main() == 0

def test_spec_prunable_threshold_4_uses_analyzer_not_manager():
    hook_source = (HOOKS_DIR / "enforce_prunable_threshold.py").read_text()
    assert "TestPruningAnalyzer" in hook_source
    assert "TestLifecycleManager" not in hook_source
    assert "TestIssueTracer" not in hook_source

def test_spec_prunable_threshold_5_threshold_imported_not_hardcoded():
    hook_source = (HOOKS_DIR / "enforce_prunable_threshold.py").read_text()
    assert "from test_lifecycle_manager import PRUNABLE_THRESHOLD" in hook_source
    tlm_source = (LIB_DIR / "test_lifecycle_manager.py").read_text()
    assert "PRUNABLE_THRESHOLD" in tlm_source

def test_spec_prunable_threshold_6_strict_mode_only():
    strict = json.loads((TEMPLATES_DIR / "settings.strict-mode.json").read_text())
    default = json.loads((TEMPLATES_DIR / "settings.default.json").read_text())
    strict_cmds = []
    for entry in strict.get("hooks", {}).get("PreCommit", []):
        for hook in entry.get("hooks", []):
            strict_cmds.append(hook.get("command", ""))
    assert any("enforce_prunable_threshold" in c for c in strict_cmds)
    default_cmds = []
    for entry in default.get("hooks", {}).get("PreCommit", []):
        for hook in entry.get("hooks", []):
            default_cmds.append(hook.get("command", ""))
    assert not any("enforce_prunable_threshold" in c for c in default_cmds)

def test_spec_prunable_threshold_7a_install_manifest():
    manifest = json.loads((CONFIG_DIR / "install_manifest.json").read_text())
    hook_files = manifest.get("components", {}).get("hooks", {}).get("files", [])
    assert any("enforce_prunable_threshold" in f for f in hook_files)

def test_spec_prunable_threshold_7b_component_classifications():
    classifications = json.loads((CONFIG_DIR / "component_classifications.json").read_text())
    hooks_section = classifications.get("classifications", {}).get("hooks", {})
    assert "enforce_prunable_threshold" in hooks_section

@patch("enforce_prunable_threshold.get_project_root")
def test_spec_prunable_threshold_8a_analyzer_exception_exits_zero(mock_root, monkeypatch):
    monkeypatch.delenv("SKIP_PRUNABLE_GATE", raising=False)
    mock_root.return_value = Path("/fake/project")
    with patch("enforce_prunable_threshold.count_prunable", side_effect=RuntimeError("crash")):
        from enforce_prunable_threshold import main
        assert main() == 0

def test_spec_prunable_threshold_8b_import_error_handled():
    hook_source = (HOOKS_DIR / "enforce_prunable_threshold.py").read_text()
    assert "except ImportError" in hook_source
    assert "sys.exit(0)" in hook_source

@patch("enforce_prunable_threshold.count_prunable")
@patch("enforce_prunable_threshold.get_project_root")
def test_spec_prunable_threshold_9_block_message_stick_carrot(mock_root, mock_count, capsys, monkeypatch):
    monkeypatch.delenv("SKIP_PRUNABLE_GATE", raising=False)
    mock_root.return_value = Path("/fake/project")
    mock_count.return_value = 200
    from enforce_prunable_threshold import main
    main()
    captured = capsys.readouterr()
    assert "REQUIRED NEXT ACTION" in captured.err

def test_spec_prunable_threshold_10_unit_test_file_exists():
    test_path = REPO_ROOT / "tests" / "unit" / "hooks" / "test_enforce_prunable_threshold.py"
    assert test_path.exists()
    source = test_path.read_text()
    test_count = source.count("def test_")
    assert test_count >= 8
