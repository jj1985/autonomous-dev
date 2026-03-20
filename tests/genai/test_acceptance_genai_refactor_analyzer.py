"""Acceptance tests for GenAI semantic analysis in /refactor (Issue #515).

Tests the hybrid static-candidate + LLM-semantic analysis pipeline:
- Doc-code drift detection via covers: frontmatter
- Hollow test classification (MEANINGFUL/HOLLOW/UNTESTED_SOURCE)
- Dead code verification with dynamic dispatch awareness
- Content hash caching
- Graceful degradation without API key
"""

import pytest

# Project root for file reads
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.mark.genai
class TestDocCodeDriftAnalysis:
    """Acceptance: doc-code drift detection flags contradictions only."""

    def test_contradiction_detection_flags_explicit_mismatch(self, genai):
        """AC: Only flags explicit contradictions, not missing documentation."""
        doc_content = (
            "The unified_pre_tool hook runs before every tool call, "
            "checking all 4 security layers for every tool."
        )
        code_content = (
            "# unified_pre_tool.py\n"
            "NATIVE_TOOLS = {'Read', 'Write', 'Edit', 'Bash', 'Glob', 'Grep'}\n"
            "def validate_mcp_security(tool_name):\n"
            "    if tool_name in NATIVE_TOOLS:\n"
            "        return  # Skip MCP security for native tools\n"
        )
        result = genai.judge(
            question="Does the documentation contain claims that contradict the code?",
            context=f"DOCUMENTATION:\n{doc_content}\n\nSOURCE CODE:\n{code_content}",
            criteria=(
                "Score 8+ if the doc contains a claim that directly contradicts the code "
                "(e.g., doc says 'all tools' but code skips native tools). "
                "Score 3-5 if ambiguous. Score 0-2 if doc and code are aligned. "
                "Only flag explicit contradictions, NOT missing docs."
            ),
            category="doc_drift",
        )
        assert result["score"] >= 6, (
            f"Should detect contradiction: doc says 'every tool' but code skips native tools. "
            f"Score: {result['score']}, Reasoning: {result['reasoning']}"
        )

    def test_non_claim_not_flagged(self, genai):
        """AC: Docs without factual claims about code are not flagged."""
        doc_content = (
            "## See Also\n\n"
            "- [Authentication guide](docs/auth.md)\n"
            "- [API reference](docs/api.md)\n"
        )
        code_content = "def authenticate(user): return True\n"
        result = genai.judge(
            question="Does the documentation contain claims that contradict the code?",
            context=f"DOCUMENTATION:\n{doc_content}\n\nSOURCE CODE:\n{code_content}",
            criteria=(
                "Score 8+ if there are NO contradictions (doc is just links/references, "
                "no factual claims about code behavior). Score 2-4 if contradictions found."
            ),
            category="doc_drift",
        )
        assert result["score"] >= 6, (
            f"Reference-only docs should not be flagged as contradictions. "
            f"Score: {result['score']}, Reasoning: {result['reasoning']}"
        )


@pytest.mark.genai
class TestHollowTestClassification:
    """Acceptance: test quality classification identifies hollow tests."""

    def test_mock_only_test_classified_hollow(self, genai):
        """AC: Mock-only and constant-assertion tests classified as HOLLOW."""
        test_code = '''
def test_process_data(mocker):
    mock_db = mocker.patch("app.database.query")
    mock_db.return_value = [{"id": 1}]
    result = mock_db()
    assert result == [{"id": 1}]  # Only asserts the mock return value
'''
        source_code = '''
def process_data(query_str: str) -> list[dict]:
    """Query database and transform results."""
    raw = database.query(query_str)
    return [{"id": r["id"], "name": r["name"].upper()} for r in raw]
'''
        result = genai.judge(
            question="Is this test MEANINGFUL or HOLLOW?",
            context=f"TEST CODE:\n{test_code}\n\nSOURCE UNDER TEST:\n{source_code}",
            criteria=(
                "Score 8+ if the test is HOLLOW — it only asserts mock return values, "
                "never exercises the real process_data function's logic (transformation). "
                "Score 2-4 if the test is MEANINGFUL — exercises real logic with real assertions."
            ),
            category="test_quality",
        )
        assert result["score"] >= 6, (
            f"Mock-only test should be classified HOLLOW. "
            f"Score: {result['score']}, Reasoning: {result['reasoning']}"
        )

    def test_meaningful_test_not_flagged(self, genai):
        """AC: Tests with real assertions on real outputs classified as MEANINGFUL."""
        test_code = '''
def test_parse_config_valid():
    config = parse_config('{"key": "value", "count": 42}')
    assert config.key == "value"
    assert config.count == 42
    assert isinstance(config, Config)

def test_parse_config_invalid():
    with pytest.raises(ValueError, match="Invalid JSON"):
        parse_config("not json")
'''
        source_code = '''
def parse_config(raw: str) -> Config:
    """Parse JSON string into Config object."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON: {raw[:50]}")
    return Config(**data)
'''
        result = genai.judge(
            question="Is this test MEANINGFUL or HOLLOW?",
            context=f"TEST CODE:\n{test_code}\n\nSOURCE UNDER TEST:\n{source_code}",
            criteria=(
                "Score 8+ if the test is MEANINGFUL — exercises real function logic, "
                "asserts specific outputs, tests error paths. "
                "Score 2-4 if the test is HOLLOW."
            ),
            category="test_quality",
        )
        assert result["score"] >= 6, (
            f"Meaningful test should not be flagged as hollow. "
            f"Score: {result['score']}, Reasoning: {result['reasoning']}"
        )


@pytest.mark.genai
class TestDeadCodeVerification:
    """Acceptance: dead code verification considers dynamic dispatch."""

    def test_decorator_registered_function_not_dead(self, genai):
        """AC: Dynamic dispatch context (decorators, getattr, __init__.py) in prompt."""
        code_context = '''
# In app/commands.py
@cli.command()
def deploy():
    """Deploy the application."""
    run_deploy_pipeline()

# In app/cli.py
cli = click.Group()
# Commands auto-discovered via @cli.command() decorator
'''
        result = genai.judge(
            question=(
                "Is the function 'deploy' dead code? It was flagged because no direct "
                "call sites (deploy()) were found via string search."
            ),
            context=code_context,
            criteria=(
                "Score 8+ if the function is NOT dead code — it's registered via "
                "@cli.command() decorator for dynamic CLI dispatch. "
                "Score 2-4 if it truly appears to be dead code."
            ),
            category="dead_code",
        )
        assert result["score"] >= 6, (
            f"Decorator-registered function should not be classified as dead code. "
            f"Score: {result['score']}, Reasoning: {result['reasoning']}"
        )


@pytest.mark.genai
class TestGracefulDegradation:
    """Acceptance: structural fallback when GenAI unavailable."""

    def test_structural_analysis_description(self, genai):
        """AC: No API key → structural fallback, no crash."""
        analyzer_spec = '''
class GenAIRefactorAnalyzer:
    def __init__(self, project_root, *, use_genai=True):
        self._structural = RefactorAnalyzer(project_root)
        self._genai_available = use_genai and _GENAI_AVAILABLE
        if not self._genai_available:
            warnings.warn("[structural-only] GenAI unavailable, using structural analysis")

    def full_analysis(self, modes=None, deep=False):
        if deep and not self._genai_available:
            raise RuntimeError("--deep requires ANTHROPIC_API_KEY")
        report = self._structural.full_analysis(modes)
        if not deep or not self._genai_available:
            return report  # structural-only
        # ... enrich with GenAI ...
'''
        result = genai.judge(
            question="Does this design correctly handle the no-API-key scenario?",
            context=analyzer_spec,
            criteria=(
                "Score 8+ if: (1) default mode falls back to structural silently, "
                "(2) --deep with no key raises explicit error, "
                "(3) no crash path. Score 4-6 if partially correct."
            ),
            category="architecture",
        )
        assert result["score"] >= 6, (
            f"Graceful degradation design should handle no-API-key correctly. "
            f"Score: {result['score']}, Reasoning: {result['reasoning']}"
        )


@pytest.mark.genai
class TestCachingBehavior:
    """Acceptance: content hash caching eliminates redundant API calls."""

    def test_cache_key_includes_content_and_model(self, genai):
        """AC: Cache at .claude/cache/refactor/ as JSON per cache key."""
        cache_design = '''
def _get_cache_key(self, file_path: Path, prompt_name: str) -> str:
    content = file_path.read_text()
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    prompt_hash = hashlib.sha256(prompt_name.encode()).hexdigest()[:8]
    model_id = self._model_id
    return hashlib.sha256(
        f"{model_id}:{prompt_hash}:{content_hash}".encode()
    ).hexdigest()
'''
        result = genai.judge(
            question="Does this cache key design correctly invalidate on content change?",
            context=cache_design,
            criteria=(
                "Score 8+ if cache key includes: file content hash (changes invalidate), "
                "model ID (model change invalidates), and prompt version (prompt change invalidates). "
                "Score 4-6 if missing one component. Score 0-3 if uses filename or mtime."
            ),
            category="architecture",
        )
        assert result["score"] >= 6, (
            f"Cache key should include content hash, model, and prompt. "
            f"Score: {result['score']}, Reasoning: {result['reasoning']}"
        )
