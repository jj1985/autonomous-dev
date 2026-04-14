"""Regression tests for iterative refinement loops (Issue #840).

Verifies that Self-Refine pattern (GENERATE → FEEDBACK → REFINE) is present
in advise.md, implement.md, and refactor.md command files.
"""
from pathlib import Path

WORKTREE_ROOT = Path(__file__).resolve().parents[2]

ADVISE_MD = WORKTREE_ROOT / "plugins/autonomous-dev/commands/advise.md"
IMPLEMENT_MD = WORKTREE_ROOT / "plugins/autonomous-dev/commands/implement.md"
REFACTOR_MD = WORKTREE_ROOT / "plugins/autonomous-dev/commands/refactor.md"


def test_advise_has_self_critique_step() -> None:
    """advise.md must contain STEP 4.5 Self-Critique FEEDBACK pass."""
    content = ADVISE_MD.read_text()
    assert "STEP 4.5" in content, "advise.md missing 'STEP 4.5'"
    assert "Self-Critique" in content, "advise.md missing 'Self-Critique'"
    assert "FEEDBACK" in content, "advise.md missing 'FEEDBACK'"


def test_implement_has_research_critique() -> None:
    """implement.md must contain STEP 4.5 Research Completeness Critique."""
    content = IMPLEMENT_MD.read_text()
    assert "STEP 4.5" in content, "implement.md missing 'STEP 4.5'"
    assert "Research Completeness Critique" in content, (
        "implement.md missing 'Research Completeness Critique'"
    )


def test_implement_reviewer_has_feedback_pass() -> None:
    """implement.md STEP 10 reviewer prompt must include a FEEDBACK pass instruction."""
    content = IMPLEMENT_MD.read_text()
    assert "FEEDBACK pass" in content, (
        "implement.md missing 'FEEDBACK pass' in STEP 10 reviewer prompt"
    )


def test_refactor_has_findings_critique() -> None:
    """refactor.md must contain STEP 1.5 Findings Self-Critique."""
    content = REFACTOR_MD.read_text()
    assert "STEP 1.5" in content, "refactor.md missing 'STEP 1.5'"
    assert "Findings Self-Critique" in content, (
        "refactor.md missing 'Findings Self-Critique'"
    )


def test_refinement_loops_follow_self_refine_pattern() -> None:
    """All four command files must contain critique/feedback keywords (Self-Refine pattern)."""
    files = {
        "advise.md": ADVISE_MD,
        "implement.md": IMPLEMENT_MD,
        "refactor.md": REFACTOR_MD,
    }
    keywords = ["critique", "Critique", "FEEDBACK", "feedback", "refine", "Refine"]
    for name, path in files.items():
        content = path.read_text()
        found = [kw for kw in keywords if kw in content]
        assert found, (
            f"{name} contains none of the Self-Refine pattern keywords: {keywords}"
        )


def test_refactor_critique_deep_mode_only() -> None:
    """refactor.md critique step must mention --deep mode only restriction."""
    content = REFACTOR_MD.read_text()
    assert "--deep" in content, (
        "refactor.md STEP 1.5 critique must reference '--deep mode only'"
    )
    assert "STEP 1.5" in content, "refactor.md missing 'STEP 1.5'"
    # Verify --deep appears near STEP 1.5
    step_15_idx = content.index("STEP 1.5")
    # Find --deep occurrence closest to STEP 1.5 (within 600 chars)
    deep_idx = content.find("--deep", step_15_idx)
    assert deep_idx != -1 and (deep_idx - step_15_idx) < 600, (
        "refactor.md STEP 1.5 does not reference '--deep' within the step block"
    )
