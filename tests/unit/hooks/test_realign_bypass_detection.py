#!/usr/bin/env python3
"""
Unit tests for realign bypass detection in unified_pre_tool.py (Issue #754).

Tests _detect_realign_bypass() for blocking raw mlx_lm/mlx.launch commands
while allowing the realign CLI wrapper and non-execution references.

Date: 2026-04-11
Agent: implementer
"""

import sys
from pathlib import Path

import pytest

# Add hooks directory to path
# tests/unit/hooks/ -> parents[3] -> repo root
sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[3]
        / "plugins"
        / "autonomous-dev"
        / "hooks"
    ),
)

from unified_pre_tool import _detect_realign_bypass


class TestRealignBypassBlocked:
    """Commands that should be blocked (raw mlx_lm execution)."""

    def test_mlx_lm_lora_command_blocked(self):
        """python -m mlx_lm.lora --model foo should be denied."""
        decision, reason = _detect_realign_bypass(
            "Bash", {"command": "python -m mlx_lm.lora --model foo --data train.jsonl"}
        )
        assert decision == "deny"
        assert "realign train" in reason
        assert "REQUIRED NEXT ACTION" in reason

    def test_mlx_launch_command_blocked(self):
        """python -m mlx.launch mlx_lm.lora should be denied."""
        decision, reason = _detect_realign_bypass(
            "Bash", {"command": "python -m mlx.launch mlx_lm.lora --model foo"}
        )
        assert decision == "deny"
        assert "BLOCKED" in reason

    def test_mlx_lm_generate_blocked(self):
        """python -m mlx_lm.generate should be denied."""
        decision, reason = _detect_realign_bypass(
            "Bash", {"command": "python -m mlx_lm.generate --model foo --prompt 'hello'"}
        )
        assert decision == "deny"
        assert "realign generate" in reason

    def test_mlx_lm_fuse_blocked(self):
        """python -m mlx_lm.fuse should be denied."""
        decision, reason = _detect_realign_bypass(
            "Bash", {"command": "python -m mlx_lm.fuse --model foo --adapter-path adapters"}
        )
        assert decision == "deny"

    def test_python3_variant_blocked(self):
        """python3 -m mlx_lm.lora should also be blocked."""
        decision, reason = _detect_realign_bypass(
            "Bash", {"command": "python3 -m mlx_lm.lora --model foo"}
        )
        assert decision == "deny"


class TestRealignBypassAllowed:
    """Commands that should be allowed (not raw mlx_lm execution)."""

    def test_realign_train_command_allowed(self):
        """realign train --model foo should be allowed."""
        decision, reason = _detect_realign_bypass(
            "Bash", {"command": "realign train --model foo --data train.jsonl"}
        )
        assert decision == "allow"
        assert reason == ""

    def test_non_bash_tool_allowed(self):
        """Non-Bash tools with mlx_lm in content should be allowed."""
        decision, reason = _detect_realign_bypass(
            "Agent", {"prompt": "Run python -m mlx_lm.lora to train"}
        )
        assert decision == "allow"

    def test_grep_for_mlx_allowed(self):
        """grep mlx_lm src/ should be allowed (search, not execution)."""
        decision, reason = _detect_realign_bypass(
            "Bash", {"command": "grep mlx_lm src/"}
        )
        assert decision == "allow"

    def test_rg_search_allowed(self):
        """rg mlx_lm.lora should be allowed (search, not execution)."""
        decision, reason = _detect_realign_bypass(
            "Bash", {"command": "rg 'mlx_lm.lora' src/realign/"}
        )
        assert decision == "allow"

    def test_cat_file_referencing_mlx_allowed(self):
        """cat of a file containing mlx_lm references should be allowed."""
        decision, reason = _detect_realign_bypass(
            "Bash", {"command": "cat src/realign/train.py"}
        )
        assert decision == "allow"

    def test_empty_command_allowed(self):
        """Empty command should be allowed."""
        decision, reason = _detect_realign_bypass(
            "Bash", {"command": ""}
        )
        assert decision == "allow"

    def test_regular_python_command_allowed(self):
        """Regular python commands should be allowed."""
        decision, reason = _detect_realign_bypass(
            "Bash", {"command": "python -m pytest tests/ -v"}
        )
        assert decision == "allow"


class TestFunctionImportable:
    """Verify the function exists and is importable."""

    def test_function_exists_and_importable(self):
        """_detect_realign_bypass should be importable from unified_pre_tool."""
        assert callable(_detect_realign_bypass)

    def test_function_returns_tuple(self):
        """Function should always return a 2-tuple."""
        result = _detect_realign_bypass("Bash", {"command": "ls"})
        assert isinstance(result, tuple)
        assert len(result) == 2
