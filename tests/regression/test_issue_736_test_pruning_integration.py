"""Regression test: Issue #736 -- test pruning analysis is available."""
from pathlib import Path
import importlib

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestTestPruningIntegration:
    def test_test_lifecycle_manager_exists(self):
        """TestLifecycleManager must exist for pruning analysis."""
        manager_path = REPO_ROOT / "plugins" / "autonomous-dev" / "lib" / "test_lifecycle_manager.py"
        assert manager_path.exists(), "test_lifecycle_manager.py must exist"

    def test_sweep_command_has_tests_flag(self):
        """sweep.md must support --tests flag."""
        sweep_path = REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "sweep.md"
        content = sweep_path.read_text()
        assert "--tests" in content, "sweep.md must support --tests flag"

    def test_lifecycle_manager_has_analyze(self):
        """TestLifecycleManager must have analyze() method."""
        import sys
        sys.path.insert(0, str(REPO_ROOT / "plugins" / "autonomous-dev" / "lib"))
        from test_lifecycle_manager import TestLifecycleManager
        assert hasattr(TestLifecycleManager, 'analyze'), "TestLifecycleManager must have analyze()"
