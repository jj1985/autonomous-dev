"""Unit tests for the Pre-Dispatch Ordering Protocol in implement.md and implement-batch.md.

Validates that both command files reference the ordering protocol correctly,
ensuring the coordinator follows ordering checks before every agent dispatch.

Issue #850: Implementer invoked before planner — ordering violations fix.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
IMPLEMENT_MD = PROJECT_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement.md"
IMPLEMENT_BATCH_MD = PROJECT_ROOT / "plugins" / "autonomous-dev" / "commands" / "implement-batch.md"


def test_implement_md_contains_ordering_protocol_section() -> None:
    """implement.md must define the Pre-Dispatch Ordering Protocol section.

    The section must contain:
    - A heading named "Pre-Dispatch Ordering Protocol"
    - The function call "check_ordering_with_session_fallback" used in the inline
      verification script

    This ensures the coordinator has a clear, named protocol to follow before
    dispatching any agent (Issue #850).
    """
    assert IMPLEMENT_MD.exists(), f"implement.md not found at {IMPLEMENT_MD}"
    content = IMPLEMENT_MD.read_text(encoding="utf-8")

    assert "Pre-Dispatch Ordering Protocol" in content, (
        "implement.md must contain a 'Pre-Dispatch Ordering Protocol' heading. "
        "This section is required by Issue #850 to catch ordering violations at dispatch time."
    )
    assert "check_ordering_with_session_fallback" in content, (
        "implement.md must contain 'check_ordering_with_session_fallback' in the ordering "
        "protocol section. This function validates agent ordering before dispatch (Issue #850)."
    )


def test_implement_md_references_protocol_at_agent_steps() -> None:
    """implement.md must reference the Pre-Dispatch Ordering Protocol at multiple agent steps.

    The protocol section heading counts as one occurrence. Each agent dispatch step
    must also reference the protocol, adding at least 4 more references.
    Total occurrences must be >= 5 to ensure broad coverage across pipeline steps.

    Expected references:
    - Protocol section definition (1)
    - STEP 4: Parallel Research
    - STEP 5: Planner
    - STEP 8: Implementer
    - STEP 8.5: Spec-Validator
    - STEP 10: Reviewer / Security-Auditor / Doc-Master
    - STEP 15: Continuous Improvement Analyst
    """
    assert IMPLEMENT_MD.exists(), f"implement.md not found at {IMPLEMENT_MD}"
    content = IMPLEMENT_MD.read_text(encoding="utf-8")

    occurrences = content.count("Pre-Dispatch Ordering Protocol")
    assert occurrences >= 5, (
        f"implement.md contains {occurrences} references to 'Pre-Dispatch Ordering Protocol', "
        f"but at least 5 are required (1 definition + 4+ step references). "
        f"Issue #850 requires the protocol to be referenced at each major agent dispatch step."
    )


def test_implement_batch_md_references_protocol() -> None:
    """implement-batch.md must reference the Pre-Dispatch Ordering Protocol.

    Batch mode runs many issues sequentially. The coordinator must follow the
    same ordering protocol for each issue's pipeline. This test ensures the
    batch command documentation explicitly references the protocol (Issue #850).
    """
    assert IMPLEMENT_BATCH_MD.exists(), f"implement-batch.md not found at {IMPLEMENT_BATCH_MD}"
    content = IMPLEMENT_BATCH_MD.read_text(encoding="utf-8")

    assert "Pre-Dispatch Ordering Protocol" in content, (
        "implement-batch.md must reference the 'Pre-Dispatch Ordering Protocol' from implement.md. "
        "Batch mode coordinators must follow the same ordering checks before each agent dispatch "
        "within each issue's pipeline (Issue #850)."
    )
