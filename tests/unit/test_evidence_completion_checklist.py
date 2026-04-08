#!/usr/bin/env python3
"""
Tests for Issue #727 - Evidence-based completion verification checklist for reviewer.

Validates that:
1. implementer.md has an Evidence Manifest Output section with required content
2. reviewer.md has an Evidence Manifest Verification section with required content
3. implement.md preserves Evidence Manifest in verbatim passing
"""

from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = PROJECT_ROOT / "plugins" / "autonomous-dev" / "agents"
COMMANDS_DIR = PROJECT_ROOT / "plugins" / "autonomous-dev" / "commands"

IMPLEMENTER_MD = AGENTS_DIR / "implementer.md"
REVIEWER_MD = AGENTS_DIR / "reviewer.md"
IMPLEMENT_MD = COMMANDS_DIR / "implement.md"


def test_implementer_has_evidence_manifest_section() -> None:
    """implementer.md must contain the Evidence Manifest Output HARD GATE section."""
    assert IMPLEMENTER_MD.exists(), f"implementer.md not found at {IMPLEMENTER_MD}"
    content = IMPLEMENTER_MD.read_text(encoding="utf-8")
    assert "Evidence Manifest Output" in content, (
        "implementer.md is missing the 'Evidence Manifest Output' section.\n"
        "Issue #727 requires implementers to output a structured evidence manifest."
    )


def test_implementer_evidence_manifest_has_forbidden_list() -> None:
    """implementer.md Evidence Manifest section must contain a FORBIDDEN list."""
    assert IMPLEMENTER_MD.exists(), f"implementer.md not found at {IMPLEMENTER_MD}"
    content = IMPLEMENTER_MD.read_text(encoding="utf-8")

    # Locate the Evidence Manifest Output section
    section_start = content.find("Evidence Manifest Output")
    assert section_start != -1, "Evidence Manifest Output section not found in implementer.md"

    # Find the next HARD GATE section after ours (to bound the search)
    next_gate = content.find("### HARD GATE:", section_start + len("Evidence Manifest Output"))
    section_content = content[section_start:next_gate] if next_gate != -1 else content[section_start:]

    # The section must contain FORBIDDEN language
    assert "FORBIDDEN" in section_content, (
        "implementer.md Evidence Manifest Output section is missing FORBIDDEN directives.\n"
        "The section must enumerate what implementers must NOT do."
    )

    # Must forbid declaring complete without an evidence manifest
    assert "implementation complete" in section_content, (
        "implementer.md Evidence Manifest Output FORBIDDEN list must prohibit "
        "declaring 'implementation complete' without an evidence manifest."
    )


def test_reviewer_has_evidence_verification_section() -> None:
    """reviewer.md must contain the Evidence Manifest Verification HARD GATE section."""
    assert REVIEWER_MD.exists(), f"reviewer.md not found at {REVIEWER_MD}"
    content = REVIEWER_MD.read_text(encoding="utf-8")
    assert "Evidence Manifest Verification" in content, (
        "reviewer.md is missing the 'Evidence Manifest Verification' section.\n"
        "Issue #727 requires reviewers to verify the implementer's evidence manifest."
    )


def test_reviewer_evidence_verification_has_forbidden_list() -> None:
    """reviewer.md Evidence Manifest Verification section must contain a FORBIDDEN list."""
    assert REVIEWER_MD.exists(), f"reviewer.md not found at {REVIEWER_MD}"
    content = REVIEWER_MD.read_text(encoding="utf-8")

    section_start = content.find("Evidence Manifest Verification")
    assert section_start != -1, "Evidence Manifest Verification section not found in reviewer.md"

    # Find the next HARD GATE section after ours
    next_gate = content.find("## HARD GATE:", section_start + len("Evidence Manifest Verification"))
    section_content = content[section_start:next_gate] if next_gate != -1 else content[section_start:]

    assert "FORBIDDEN" in section_content, (
        "reviewer.md Evidence Manifest Verification section is missing FORBIDDEN directives.\n"
        "The section must enumerate what reviewers must NOT do."
    )

    # Must forbid issuing APPROVE without completing evidence verification
    assert "APPROVE" in section_content, (
        "reviewer.md Evidence Manifest Verification FORBIDDEN list must address "
        "issuing APPROVE without completing evidence verification."
    )


def test_reviewer_blocks_missing_manifest() -> None:
    """reviewer.md must document that a missing evidence manifest triggers REQUEST_CHANGES."""
    assert REVIEWER_MD.exists(), f"reviewer.md not found at {REVIEWER_MD}"
    content = REVIEWER_MD.read_text(encoding="utf-8")

    section_start = content.find("Evidence Manifest Verification")
    assert section_start != -1, "Evidence Manifest Verification section not found in reviewer.md"

    next_gate = content.find("## HARD GATE:", section_start + len("Evidence Manifest Verification"))
    section_content = content[section_start:next_gate] if next_gate != -1 else content[section_start:]

    # Must instruct reviewer to issue REQUEST_CHANGES when manifest is missing
    assert "REQUEST_CHANGES" in section_content, (
        "reviewer.md Evidence Manifest Verification section must specify that "
        "a missing evidence manifest results in REQUEST_CHANGES verdict."
    )

    # Must address the case of no manifest present in implementer output
    assert "missing" in section_content.lower() or "no " in section_content.lower(), (
        "reviewer.md Evidence Manifest Verification section must address "
        "how to handle a missing/absent evidence manifest from the implementer."
    )


def test_implement_preserves_evidence_manifest_in_passthrough() -> None:
    """implement.md VERBATIM PASSING section must instruct coordinators to preserve Evidence Manifest."""
    assert IMPLEMENT_MD.exists(), f"implement.md not found at {IMPLEMENT_MD}"
    content = IMPLEMENT_MD.read_text(encoding="utf-8")

    # The VERBATIM PASSING instructions must mention preserving the Evidence Manifest
    assert "Evidence Manifest" in content, (
        "implement.md does not mention 'Evidence Manifest' in the VERBATIM PASSING instructions.\n"
        "Issue #727 requires coordinators to preserve the Evidence Manifest when passing "
        "implementer output to the reviewer."
    )

    # Find the VERBATIM PASSING section context
    verbatim_idx = content.find("VERBATIM PASSING REQUIRED")
    assert verbatim_idx != -1, "implement.md is missing the VERBATIM PASSING REQUIRED section"

    # Check that Evidence Manifest is mentioned near the VERBATIM PASSING section
    # Look within a 1000-character window around the first occurrence
    window = content[verbatim_idx: verbatim_idx + 1000]
    assert "Evidence Manifest" in window, (
        "implement.md mentions Evidence Manifest but not in the VERBATIM PASSING section.\n"
        "The Evidence Manifest preservation instruction must appear in the VERBATIM PASSING "
        "section so coordinators know to preserve it when truncating long output."
    )
