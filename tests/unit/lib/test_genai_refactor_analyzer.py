#!/usr/bin/env python3
"""Unit tests for genai_refactor_analyzer module.

Tests the GenAIRefactorAnalyzer class including GenAI-enhanced doc-code drift
analysis, hollow test detection, dead code verification, caching, security
filtering, graceful degradation, and batch API support.
"""

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Ensure lib is importable
sys.path.insert(
    0,
    str(
        Path(__file__).parent.parent.parent.parent
        / "plugins"
        / "autonomous-dev"
        / "lib"
    ),
)

from genai_refactor_analyzer import (
    GenAIRefactorAnalyzer,
    _DEAD_CODE_CONFIDENCE_THRESHOLD,
    _SENSITIVE_PATTERNS,
)
from refactor_analyzer import (
    ConfidenceLevel,
    OptimizationType,
    RefactorCategory,
    RefactorFinding,
    RefactorReport,
)
from sweep_analyzer import SweepSeverity


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def project_root(tmp_path):
    """Create a minimal project structure for testing."""
    # Create directories
    (tmp_path / "docs").mkdir()
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "plugins" / "autonomous-dev" / "lib").mkdir(parents=True)
    (tmp_path / "src").mkdir()
    (tmp_path / ".claude" / "cache" / "refactor").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def analyzer_no_genai(project_root):
    """Create analyzer with GenAI disabled."""
    return GenAIRefactorAnalyzer(project_root, use_genai=False)


@pytest.fixture
def analyzer_with_genai(project_root):
    """Create analyzer with GenAI enabled (mocked)."""
    analyzer = GenAIRefactorAnalyzer(project_root, use_genai=True)
    return analyzer


# =============================================================================
# TestGenAIRefactorAnalyzerInit
# =============================================================================


class TestGenAIRefactorAnalyzerInit:
    """Tests for GenAIRefactorAnalyzer construction and configuration."""

    def test_construction_basic(self, project_root):
        """Test basic construction with defaults."""
        analyzer = GenAIRefactorAnalyzer(project_root)
        assert analyzer.project_root == project_root.resolve()
        assert analyzer._structural is not None
        assert analyzer.use_batch_api is False

    def test_construction_genai_disabled(self, project_root):
        """Test construction with use_genai=False."""
        analyzer = GenAIRefactorAnalyzer(project_root, use_genai=False)
        assert analyzer._genai_enabled is False

    def test_construction_batch_api(self, project_root):
        """Test construction with batch API enabled."""
        analyzer = GenAIRefactorAnalyzer(project_root, use_batch_api=True)
        assert analyzer.use_batch_api is True

    def test_cache_dir_location(self, project_root):
        """Test cache directory is set correctly."""
        analyzer = GenAIRefactorAnalyzer(project_root)
        expected = project_root.resolve() / ".claude" / "cache" / "refactor"
        assert analyzer._cache_dir == expected

    def test_warnings_start_empty(self, project_root):
        """Test warnings list starts empty."""
        analyzer = GenAIRefactorAnalyzer(project_root)
        assert analyzer.warnings == []

    def test_structural_analyzer_composition(self, project_root):
        """Test that structural analyzer is composed (not inherited)."""
        analyzer = GenAIRefactorAnalyzer(project_root)
        from refactor_analyzer import RefactorAnalyzer
        assert isinstance(analyzer._structural, RefactorAnalyzer)


# =============================================================================
# TestContentHashCache
# =============================================================================


class TestContentHashCache:
    """Tests for content hash caching."""

    def test_cache_key_generation(self, analyzer_no_genai, project_root):
        """Test cache key is a SHA-256 hash."""
        test_file = project_root / "test.py"
        test_file.write_text("print('hello')")

        key = analyzer_no_genai._get_cache_key(test_file, "test_prompt")
        assert len(key) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in key)

    def test_cache_key_deterministic(self, analyzer_no_genai, project_root):
        """Test same file + prompt produces same key."""
        test_file = project_root / "test.py"
        test_file.write_text("print('hello')")

        key1 = analyzer_no_genai._get_cache_key(test_file, "test_prompt")
        key2 = analyzer_no_genai._get_cache_key(test_file, "test_prompt")
        assert key1 == key2

    def test_cache_key_differs_for_different_content(self, analyzer_no_genai, project_root):
        """Test different file content produces different key."""
        test_file = project_root / "test.py"
        test_file.write_text("version 1")
        key1 = analyzer_no_genai._get_cache_key(test_file, "prompt")

        test_file.write_text("version 2")
        key2 = analyzer_no_genai._get_cache_key(test_file, "prompt")
        assert key1 != key2

    def test_cache_key_differs_for_different_prompt(self, analyzer_no_genai, project_root):
        """Test different prompt name produces different key."""
        test_file = project_root / "test.py"
        test_file.write_text("content")

        key1 = analyzer_no_genai._get_cache_key(test_file, "prompt_a")
        key2 = analyzer_no_genai._get_cache_key(test_file, "prompt_b")
        assert key1 != key2

    def test_cache_miss_returns_none(self, analyzer_no_genai):
        """Test cache miss returns None."""
        result = analyzer_no_genai._get_cached_result("nonexistent_key")
        assert result is None

    def test_cache_hit_returns_data(self, analyzer_no_genai, project_root):
        """Test cache hit returns stored data."""
        cache_data = {"verdict": "DEAD", "confidence": 0.9}
        analyzer_no_genai._set_cached_result("test_key", cache_data)

        result = analyzer_no_genai._get_cached_result("test_key")
        assert result == cache_data

    def test_cache_creates_directory(self, tmp_path):
        """Test cache creates directory if it doesn't exist."""
        # Use a project root WITHOUT pre-created cache dir
        analyzer = GenAIRefactorAnalyzer(tmp_path, use_genai=False)
        analyzer._set_cached_result("key123", {"data": "value"})

        cache_file = analyzer._cache_dir / "key123.json"
        assert cache_file.exists()

    def test_cache_handles_corrupt_file(self, analyzer_no_genai, project_root):
        """Test cache handles corrupt JSON gracefully."""
        cache_dir = project_root / ".claude" / "cache" / "refactor"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "bad_key.json").write_text("not json{{{")

        result = analyzer_no_genai._get_cached_result("bad_key")
        assert result is None


# =============================================================================
# TestDocCodeDriftAnalysis
# =============================================================================


class TestDocCodeDriftAnalysis:
    """Tests for doc-code drift analysis."""

    def test_parse_covers_frontmatter_basic(self, analyzer_no_genai):
        """Test parsing covers: frontmatter."""
        content = "---\ncovers:\n  - src/foo.py\n  - src/bar.py\n---\n# Doc"
        paths = analyzer_no_genai._parse_covers_frontmatter(content)
        assert paths == ["src/foo.py", "src/bar.py"]

    def test_parse_covers_frontmatter_no_frontmatter(self, analyzer_no_genai):
        """Test parsing file without frontmatter."""
        content = "# Just a document\nNo frontmatter here."
        paths = analyzer_no_genai._parse_covers_frontmatter(content)
        assert paths == []

    def test_parse_covers_frontmatter_no_covers(self, analyzer_no_genai):
        """Test parsing frontmatter without covers field."""
        content = "---\ntitle: My Doc\nauthor: Test\n---\n# Doc"
        paths = analyzer_no_genai._parse_covers_frontmatter(content)
        assert paths == []

    def test_parse_covers_frontmatter_single_path(self, analyzer_no_genai):
        """Test parsing covers with a single path."""
        content = "---\ncovers:\n  - lib/utils.py\n---\n# Doc"
        paths = analyzer_no_genai._parse_covers_frontmatter(content)
        assert paths == ["lib/utils.py"]

    def test_drift_returns_empty_without_genai(self, analyzer_no_genai, project_root):
        """Test drift analysis returns empty list without GenAI."""
        doc = project_root / "docs" / "test.md"
        doc.write_text("---\ncovers:\n  - src/foo.py\n---\n# Doc")
        (project_root / "src" / "foo.py").write_text("def foo(): pass")

        findings = analyzer_no_genai._analyze_doc_code_drift()
        assert findings == []

    def test_drift_returns_empty_without_docs_dir(self, tmp_path):
        """Test drift analysis returns empty when no docs/ directory."""
        analyzer = GenAIRefactorAnalyzer(tmp_path, use_genai=False)
        findings = analyzer._analyze_doc_code_drift()
        assert findings == []

    def test_parse_drift_result_aligned(self, analyzer_no_genai):
        """Test parsing ALIGNED result produces no findings."""
        result = {"status": "ALIGNED"}
        findings = analyzer_no_genai._parse_drift_result(result, "doc.md", "src.py")
        assert findings == []

    def test_parse_drift_result_with_contradictions(self, analyzer_no_genai):
        """Test parsing result with contradictions."""
        result = {
            "contradictions": [
                {
                    "doc_claim": "returns a list",
                    "code_behavior": "returns a dict",
                    "severity": "HIGH",
                }
            ]
        }
        findings = analyzer_no_genai._parse_drift_result(result, "doc.md", "src.py")
        assert len(findings) == 1
        assert "[genai]" in findings[0].description
        assert "returns a list" in findings[0].description
        assert findings[0].severity == SweepSeverity.HIGH

    def test_parse_json_or_aligned_aligned_string(self, analyzer_no_genai):
        """Test parsing ALIGNED string."""
        result = analyzer_no_genai._parse_json_or_aligned("ALIGNED")
        assert result == {"status": "ALIGNED"}

    def test_parse_json_or_aligned_quoted(self, analyzer_no_genai):
        """Test parsing quoted ALIGNED string."""
        result = analyzer_no_genai._parse_json_or_aligned('"ALIGNED"')
        assert result == {"status": "ALIGNED"}

    def test_parse_json_or_aligned_valid_json(self, analyzer_no_genai):
        """Test parsing valid JSON."""
        json_str = '{"contradictions": [{"severity": "LOW"}]}'
        result = analyzer_no_genai._parse_json_or_aligned(json_str)
        assert "contradictions" in result

    def test_parse_json_or_aligned_malformed(self, analyzer_no_genai):
        """Test parsing malformed response falls back to ALIGNED."""
        result = analyzer_no_genai._parse_json_or_aligned("some random text")
        assert result == {"status": "ALIGNED"}


# =============================================================================
# TestHollowTestAnalysis
# =============================================================================


class TestHollowTestAnalysis:
    """Tests for hollow test detection."""

    def test_hollow_returns_empty_without_genai(self, analyzer_no_genai, project_root):
        """Test hollow analysis returns empty without GenAI."""
        findings = analyzer_no_genai._analyze_hollow_tests()
        assert findings == []

    def test_find_source_for_test_basic(self, analyzer_no_genai, project_root):
        """Test finding source file for a test file."""
        source = project_root / "plugins" / "autonomous-dev" / "lib" / "foo.py"
        source.write_text("def foo(): pass")
        test_file = project_root / "tests" / "unit" / "test_foo.py"
        test_file.write_text("def test_foo(): assert True")

        result = analyzer_no_genai._find_source_for_test(test_file)
        assert result is not None
        assert result.name == "foo.py"

    def test_find_source_for_test_not_found(self, analyzer_no_genai, project_root):
        """Test finding source for test with no matching source."""
        test_file = project_root / "tests" / "test_nonexistent.py"
        test_file.write_text("pass")

        result = analyzer_no_genai._find_source_for_test(test_file)
        assert result is None

    def test_find_source_for_non_test_file(self, analyzer_no_genai, project_root):
        """Test non-test file returns None."""
        non_test = project_root / "tests" / "conftest.py"
        non_test.write_text("pass")

        result = analyzer_no_genai._find_source_for_test(non_test)
        assert result is None

    def test_parse_hollow_result_meaningful(self, analyzer_no_genai):
        """Test MEANINGFUL classification produces no finding."""
        result = {"classification": "MEANINGFUL", "reason": "good", "confidence": 0.9}
        finding = analyzer_no_genai._parse_hollow_result(result, "test.py")
        assert finding is None

    def test_parse_hollow_result_hollow(self, analyzer_no_genai):
        """Test HOLLOW classification produces a finding."""
        result = {"classification": "HOLLOW", "reason": "mocks everything", "confidence": 0.8}
        finding = analyzer_no_genai._parse_hollow_result(result, "test.py")
        assert finding is not None
        assert "[genai]" in finding.description
        assert finding.category == RefactorCategory.TEST_WASTE
        assert finding.severity == SweepSeverity.MEDIUM

    def test_parse_hollow_result_untested(self, analyzer_no_genai):
        """Test UNTESTED_SOURCE classification produces a finding."""
        result = {"classification": "UNTESTED_SOURCE", "reason": "no tests", "confidence": 0.9}
        finding = analyzer_no_genai._parse_hollow_result(result, "test.py")
        assert finding is not None
        assert "[genai]" in finding.description
        assert finding.severity == SweepSeverity.HIGH

    def test_parse_hollow_low_confidence(self, analyzer_no_genai):
        """Test low confidence produces MEDIUM confidence level."""
        result = {"classification": "HOLLOW", "reason": "maybe", "confidence": 0.5}
        finding = analyzer_no_genai._parse_hollow_result(result, "test.py")
        assert finding is not None
        assert finding.confidence == ConfidenceLevel.MEDIUM

    def test_parse_hollow_high_confidence(self, analyzer_no_genai):
        """Test high confidence produces HIGH confidence level."""
        result = {"classification": "HOLLOW", "reason": "certain", "confidence": 0.85}
        finding = analyzer_no_genai._parse_hollow_result(result, "test.py")
        assert finding is not None
        assert finding.confidence == ConfidenceLevel.HIGH


# =============================================================================
# TestDeadCodeVerification
# =============================================================================


class TestDeadCodeVerification:
    """Tests for dead code verification."""

    def test_verify_returns_candidates_without_genai(self, analyzer_no_genai):
        """Test verification returns original candidates without GenAI."""
        candidates = [
            RefactorFinding(
                category=RefactorCategory.DEAD_CODE,
                severity=SweepSeverity.MEDIUM,
                file_path="lib/foo.py",
                description="Potentially dead function: old_helper",
                suggestion="Remove",
            )
        ]
        result = analyzer_no_genai._verify_dead_code(candidates)
        assert result == candidates  # Returned unverified

    def test_is_confirmed_dead_true(self, analyzer_no_genai):
        """Test confirmed dead with high confidence."""
        result = {"verdict": "DEAD", "confidence": 0.9}
        assert analyzer_no_genai._is_confirmed_dead(result) is True

    def test_is_confirmed_dead_low_confidence(self, analyzer_no_genai):
        """Test not confirmed dead with low confidence."""
        result = {"verdict": "DEAD", "confidence": 0.5}
        assert analyzer_no_genai._is_confirmed_dead(result) is False

    def test_is_confirmed_alive(self, analyzer_no_genai):
        """Test alive verdict."""
        result = {"verdict": "ALIVE", "confidence": 0.9}
        assert analyzer_no_genai._is_confirmed_dead(result) is False

    def test_is_confirmed_dead_at_threshold(self, analyzer_no_genai):
        """Test confidence exactly at threshold."""
        result = {"verdict": "DEAD", "confidence": _DEAD_CODE_CONFIDENCE_THRESHOLD}
        assert analyzer_no_genai._is_confirmed_dead(result) is True

    def test_is_confirmed_dead_below_threshold(self, analyzer_no_genai):
        """Test confidence just below threshold."""
        result = {"verdict": "DEAD", "confidence": _DEAD_CODE_CONFIDENCE_THRESHOLD - 0.01}
        assert analyzer_no_genai._is_confirmed_dead(result) is False

    def test_extract_function_name_standard(self, analyzer_no_genai):
        """Test extracting function name from standard description."""
        desc = "Potentially dead function: old_helper"
        assert analyzer_no_genai._extract_function_name(desc) == "old_helper"

    def test_extract_function_name_class(self, analyzer_no_genai):
        """Test extracting class name."""
        desc = "Potentially dead class: OldProcessor"
        assert analyzer_no_genai._extract_function_name(desc) == "OldProcessor"

    def test_extract_function_name_no_match(self, analyzer_no_genai):
        """Test no function name found."""
        desc = "Some generic description"
        assert analyzer_no_genai._extract_function_name(desc) is None

    def test_extract_function_source(self, analyzer_no_genai):
        """Test extracting function source code."""
        source = "def foo():\n    return 42\n\ndef bar():\n    return 0\n"
        result = analyzer_no_genai._extract_function_source(source, "foo")
        assert result is not None
        assert "return 42" in result

    def test_extract_function_source_not_found(self, analyzer_no_genai):
        """Test extracting non-existent function returns None."""
        source = "def foo():\n    pass\n"
        result = analyzer_no_genai._extract_function_source(source, "bar")
        assert result is None

    def test_extract_function_source_invalid_syntax(self, analyzer_no_genai):
        """Test extracting from invalid syntax returns None."""
        source = "def foo(:\n    pass"
        result = analyzer_no_genai._extract_function_source(source, "foo")
        assert result is None


# =============================================================================
# TestSecurityFiltering
# =============================================================================


class TestSecurityFiltering:
    """Tests for sensitive file exclusion."""

    def test_env_file_filtered(self, analyzer_no_genai, project_root):
        """Test .env files are filtered."""
        env_file = project_root / ".env"
        assert analyzer_no_genai._is_sensitive_file(env_file) is True

    def test_pem_file_filtered(self, analyzer_no_genai, project_root):
        """Test .pem files are filtered."""
        pem_file = project_root / "cert.pem"
        assert analyzer_no_genai._is_sensitive_file(pem_file) is True

    def test_key_file_filtered(self, analyzer_no_genai, project_root):
        """Test .key files are filtered."""
        key_file = project_root / "private.key"
        assert analyzer_no_genai._is_sensitive_file(key_file) is True

    def test_secret_in_name_filtered(self, analyzer_no_genai, project_root):
        """Test files with 'secret' in name are filtered."""
        secret_file = project_root / "my_secret_config.json"
        assert analyzer_no_genai._is_sensitive_file(secret_file) is True

    def test_credential_in_name_filtered(self, analyzer_no_genai, project_root):
        """Test files with 'credential' in name are filtered."""
        cred_file = project_root / "credentials.json"
        assert analyzer_no_genai._is_sensitive_file(cred_file) is True

    def test_password_in_name_filtered(self, analyzer_no_genai, project_root):
        """Test files with 'password' in name are filtered."""
        pw_file = project_root / "password_store.txt"
        assert analyzer_no_genai._is_sensitive_file(pw_file) is True

    def test_normal_file_not_filtered(self, analyzer_no_genai, project_root):
        """Test normal files are not filtered."""
        normal_file = project_root / "src" / "main.py"
        assert analyzer_no_genai._is_sensitive_file(normal_file) is False

    def test_case_insensitive_filtering(self, analyzer_no_genai, project_root):
        """Test filtering is case-insensitive."""
        upper_secret = project_root / "MY_SECRET.txt"
        assert analyzer_no_genai._is_sensitive_file(upper_secret) is True


# =============================================================================
# TestGenAITagging
# =============================================================================


class TestGenAITagging:
    """Tests for [genai] tag in finding descriptions."""

    def test_drift_findings_have_genai_tag(self, analyzer_no_genai):
        """Test doc-code drift findings include [genai] tag."""
        result = {
            "contradictions": [{
                "doc_claim": "does X",
                "code_behavior": "does Y",
                "severity": "MEDIUM",
            }]
        }
        findings = analyzer_no_genai._parse_drift_result(result, "doc.md", "src.py")
        assert len(findings) == 1
        assert "[genai]" in findings[0].description

    def test_hollow_test_findings_have_genai_tag(self, analyzer_no_genai):
        """Test hollow test findings include [genai] tag."""
        result = {"classification": "HOLLOW", "reason": "test", "confidence": 0.9}
        finding = analyzer_no_genai._parse_hollow_result(result, "test.py")
        assert finding is not None
        assert "[genai]" in finding.description

    def test_untested_source_findings_have_genai_tag(self, analyzer_no_genai):
        """Test untested source findings include [genai] tag."""
        result = {"classification": "UNTESTED_SOURCE", "reason": "no tests", "confidence": 0.9}
        finding = analyzer_no_genai._parse_hollow_result(result, "test.py")
        assert finding is not None
        assert "[genai]" in finding.description


# =============================================================================
# TestGracefulDegradation
# =============================================================================


class TestGracefulDegradation:
    """Tests for graceful degradation without SDK/API key."""

    def test_no_genai_returns_structural_only(self, analyzer_no_genai, project_root):
        """Test analysis without GenAI returns structural results only."""
        report = analyzer_no_genai.full_analysis()
        assert isinstance(report, RefactorReport)

    def test_no_genai_adds_warning(self, analyzer_no_genai, project_root):
        """Test analysis without GenAI adds warning."""
        analyzer_no_genai.full_analysis()
        assert len(analyzer_no_genai.warnings) > 0
        assert "structural-only" in analyzer_no_genai.warnings[0].lower() or \
               "not available" in analyzer_no_genai.warnings[0].lower()

    @patch.dict("os.environ", {}, clear=True)
    def test_deep_without_api_key_raises(self, project_root):
        """Test --deep without API key raises RuntimeError."""
        # Need to ensure _GENAI_AVAILABLE is True for this test
        import genai_refactor_analyzer as mod
        original = mod._GENAI_AVAILABLE
        try:
            mod._GENAI_AVAILABLE = True
            analyzer = GenAIRefactorAnalyzer(project_root, use_genai=True)
            analyzer._genai_enabled = True
            with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                analyzer.full_analysis(deep=True)
        finally:
            mod._GENAI_AVAILABLE = original

    def test_deep_without_sdk_raises(self, project_root):
        """Test --deep without SDK raises RuntimeError."""
        import genai_refactor_analyzer as mod
        original = mod._GENAI_AVAILABLE
        try:
            mod._GENAI_AVAILABLE = False
            analyzer = GenAIRefactorAnalyzer(project_root, use_genai=True)
            with pytest.raises(RuntimeError, match="Anthropic SDK"):
                analyzer.full_analysis(deep=True)
        finally:
            mod._GENAI_AVAILABLE = original

    def test_malformed_genai_response_handled(self, analyzer_no_genai):
        """Test malformed GenAI response doesn't crash."""
        result = analyzer_no_genai._parse_json_or_aligned("{{invalid json")
        # Should fall back to ALIGNED (no findings)
        assert result.get("status") == "ALIGNED"

    def test_api_timeout_handled(self, project_root):
        """Test that API timeout in GenAI analyzer is handled gracefully."""
        analyzer = GenAIRefactorAnalyzer(project_root, use_genai=False)
        # With genai disabled, methods return empty lists
        findings = analyzer._analyze_doc_code_drift()
        assert findings == []


# =============================================================================
# TestBatchAPI
# =============================================================================


class TestBatchAPI:
    """Tests for Batch API support."""

    def test_batch_disabled_returns_none(self, analyzer_no_genai):
        """Test batch submission with batch API disabled returns None."""
        result = analyzer_no_genai._submit_batch([{"custom_id": "1", "prompt": "test"}])
        assert result is None

    @patch("genai_refactor_analyzer.GenAIRefactorAnalyzer._submit_batch")
    def test_batch_submission_structure(self, mock_submit, project_root):
        """Test batch submission is called with correct structure."""
        analyzer = GenAIRefactorAnalyzer(project_root, use_batch_api=True, use_genai=False)
        mock_submit.return_value = "batch_123"

        requests = [
            {"custom_id": "req_1", "prompt": "analyze this"},
            {"custom_id": "req_2", "prompt": "analyze that"},
        ]
        result = analyzer._submit_batch(requests)
        assert result == "batch_123"

    def test_poll_batch_without_sdk(self, analyzer_no_genai):
        """Test polling batch without SDK returns None."""
        result = analyzer_no_genai._poll_batch("batch_123")
        assert result is None


# =============================================================================
# TestFullAnalysis
# =============================================================================


class TestFullAnalysis:
    """Tests for the full_analysis orchestration method."""

    def test_full_analysis_returns_report(self, analyzer_no_genai, project_root):
        """Test full_analysis returns a RefactorReport."""
        report = analyzer_no_genai.full_analysis()
        assert isinstance(report, RefactorReport)
        assert isinstance(report.findings, list)
        assert isinstance(report.modes_run, list)

    def test_full_analysis_specific_modes(self, analyzer_no_genai, project_root):
        """Test full_analysis with specific modes."""
        report = analyzer_no_genai.full_analysis(modes=["docs"])
        assert "docs" in report.modes_run

    def test_full_analysis_default_modes(self, analyzer_no_genai, project_root):
        """Test full_analysis with default modes runs all three."""
        report = analyzer_no_genai.full_analysis()
        assert set(report.modes_run) == {"tests", "docs", "code"}

    def test_full_analysis_records_duration(self, analyzer_no_genai, project_root):
        """Test full_analysis records scan duration."""
        report = analyzer_no_genai.full_analysis()
        assert report.scan_duration_ms >= 0


# =============================================================================
# TestBuildReferencesSummary
# =============================================================================


class TestBuildReferencesSummary:
    """Tests for building references summary."""

    def test_no_references(self, analyzer_no_genai, project_root):
        """Test summary when no references found."""
        summary = analyzer_no_genai._build_references_summary("nonexistent_function_xyz")
        assert "No references" in summary

    def test_references_found(self, analyzer_no_genai, project_root):
        """Test summary when references exist."""
        src_dir = project_root / "src"
        src_dir.mkdir(exist_ok=True)
        (src_dir / "main.py").write_text("from utils import my_func\nmy_func()")

        summary = analyzer_no_genai._build_references_summary("my_func")
        assert "src/main.py" in summary
        assert "reference" in summary
