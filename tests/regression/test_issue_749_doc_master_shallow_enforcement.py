"""Regression test: Issue #749 — doc-master output too shallow (54 words vs 100 minimum).

Verifies that all doc-master invocation and collection points enforce the 100-word minimum
and include shallow detection with retry logic.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENT_CMD = REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement.md"
IMPLEMENT_FIX_CMD = REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement-fix.md"
IMPLEMENT_BATCH_CMD = REPO_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement-batch.md"
DOC_MASTER_AGENT = REPO_ROOT / "plugins" / "autonomous-dev" / "agents" / "doc-master.md"

WORD_THRESHOLD = 100


class TestDocMasterShallowEnforcementImplementMd:
    """Validate implement.md (full pipeline) has shallow detection with retry."""

    def setup_method(self):
        self.content = IMPLEMENT_CMD.read_text()

    def test_implement_md_has_shallow_detection_with_retry(self):
        """implement.md must have DOC-VERDICT-SHALLOW detection at the collection point."""
        assert "DOC-VERDICT-SHALLOW" in self.content, (
            "implement.md is missing DOC-VERDICT-SHALLOW shallow detection at the doc-master collection point"
        )

    def test_implement_md_has_100_word_minimum(self):
        """implement.md must reference the 100-word minimum threshold."""
        assert re.search(r"100\s+words", self.content), (
            "implement.md must specify the 100-word minimum for doc-master output"
        )

    def test_implement_md_has_shallow_retry(self):
        """implement.md must describe a retry on shallow output."""
        assert "DOC-VERDICT-SHALLOW-RETRY-FAILED" in self.content, (
            "implement.md must include DOC-VERDICT-SHALLOW-RETRY-FAILED log marker for retry exhaustion"
        )


class TestDocMasterShallowEnforcementImplementFixMd:
    """Validate implement-fix.md (fix pipeline) has shallow detection."""

    def setup_method(self):
        self.content = IMPLEMENT_FIX_CMD.read_text()

    def test_implement_fix_md_has_shallow_detection(self):
        """implement-fix.md must have DOC-VERDICT-SHALLOW detection."""
        assert "DOC-VERDICT-SHALLOW" in self.content, (
            "implement-fix.md is missing DOC-VERDICT-SHALLOW shallow detection at the doc-master collection point"
        )

    def test_implement_fix_md_has_100_word_minimum(self):
        """implement-fix.md must reference the 100-word minimum threshold."""
        assert re.search(r"100\s+words", self.content), (
            "implement-fix.md must specify the 100-word minimum for doc-master output"
        )

    def test_implement_fix_md_has_shallow_retry_failed_marker(self):
        """implement-fix.md must include retry-failed log marker."""
        assert "DOC-VERDICT-SHALLOW-RETRY-FAILED" in self.content, (
            "implement-fix.md must include DOC-VERDICT-SHALLOW-RETRY-FAILED log marker"
        )


class TestDocMasterShallowEnforcementImplementBatchMd:
    """Validate implement-batch.md (batch pipeline) has shallow detection."""

    def setup_method(self):
        self.content = IMPLEMENT_BATCH_CMD.read_text()

    def test_implement_batch_md_has_shallow_detection(self):
        """implement-batch.md must have DOC-VERDICT-SHALLOW detection."""
        assert "DOC-VERDICT-SHALLOW" in self.content, (
            "implement-batch.md is missing DOC-VERDICT-SHALLOW shallow detection at the per-issue doc-drift collection point"
        )

    def test_implement_batch_md_has_100_word_minimum(self):
        """implement-batch.md must reference the 100-word minimum threshold."""
        assert re.search(r"100\s+words", self.content), (
            "implement-batch.md must specify the 100-word minimum for doc-master output"
        )

    def test_implement_batch_md_has_shallow_as_verdict_value(self):
        """implement-batch.md must include SHALLOW as a possible recorded verdict."""
        assert "doc-drift-verdict: SHALLOW" in self.content or "SHALLOW" in self.content, (
            "implement-batch.md must record SHALLOW as a possible doc-drift-verdict value"
        )


class TestDocMasterAgentMinimumOutputRequirement:
    """Validate doc-master agent prompt enforces 100-word minimum output."""

    def setup_method(self):
        self.content = DOC_MASTER_AGENT.read_text()

    def test_doc_master_has_minimum_output_requirement(self):
        """doc-master.md must have a HARD GATE for minimum 100-word output."""
        assert "100 words" in self.content or re.search(r"minimum.*100", self.content, re.IGNORECASE), (
            "doc-master.md must include a minimum 100-word output requirement"
        )

    def test_doc_master_forbidden_list_includes_shallow_output(self):
        """doc-master.md FORBIDDEN list must prohibit outputs under 100 words."""
        # The FORBIDDEN section must mention the 100-word limit
        assert re.search(r"100\s+words", self.content), (
            "doc-master.md FORBIDDEN section must prohibit producing output under 100 words"
        )

    def test_doc_master_references_issue_749(self):
        """doc-master.md must reference Issue #749 to track the origin of this enforcement."""
        assert "749" in self.content, (
            "doc-master.md must reference Issue #749 in the shallow output FORBIDDEN entry"
        )


class TestAllCollectionPointsUseSameThreshold:
    """All three collection points must use the same 100-word threshold."""

    def test_all_collection_points_use_same_threshold(self):
        """implement.md, implement-fix.md, and implement-batch.md must all use 100 words."""
        threshold_pattern = re.compile(r"(\d+)\s+words")

        for cmd_file, label in [
            (IMPLEMENT_CMD, "implement.md"),
            (IMPLEMENT_FIX_CMD, "implement-fix.md"),
            (IMPLEMENT_BATCH_CMD, "implement-batch.md"),
        ]:
            content = cmd_file.read_text()
            matches = threshold_pattern.findall(content)
            thresholds = {int(m) for m in matches}
            assert WORD_THRESHOLD in thresholds, (
                f"{label} does not contain the {WORD_THRESHOLD}-word threshold "
                f"(found: {sorted(thresholds)})"
            )
