"""Validator for doc-master DOC-DRIFT-VERDICT output.

Provides a reusable function to parse doc-master output and check whether
a valid DOC-DRIFT-VERDICT line is present. Used by the coordinator to
detect missing verdicts before the pipeline completes (Issue #602).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Minimum word count for doc-master output to be considered substantive
MIN_DOC_VERDICT_WORDS = 100

# Regex to match DOC-DRIFT-VERDICT lines, with optional ANSI escape codes
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
_VERDICT_PATTERN = re.compile(
    r"^DOC-DRIFT-VERDICT:\s*(PASS|FAIL(?:\((\w*)\))?)$"
)


@dataclass
class DocVerdictResult:
    """Result of parsing doc-master output for DOC-DRIFT-VERDICT.

    Attributes:
        found: Whether a DOC-DRIFT-VERDICT line was found anywhere in the output.
        verdict: "PASS", "FAIL", or "" if not found.
        finding_count: Number of findings from FAIL(N). -1 if parse error, 0 for PASS.
        raw_line: The actual verdict line found (after stripping ANSI/whitespace).
        position_warning: Non-empty if verdict was found but is not the last
            non-empty line of the output.
    """

    found: bool
    verdict: str
    finding_count: int
    raw_line: str
    position_warning: str
    word_count: int = 0
    is_shallow: bool = False


def validate_doc_verdict(doc_master_output: str) -> DocVerdictResult:
    """Parse doc-master output for DOC-DRIFT-VERDICT line.

    Scans the full output for verdict lines. If multiple are found, uses the
    last one. Checks whether the verdict appears as the final non-empty line
    and sets position_warning if not.

    Args:
        doc_master_output: The complete text output from doc-master.

    Returns:
        DocVerdictResult with parsing results.
    """
    if not doc_master_output or not doc_master_output.strip():
        return DocVerdictResult(
            found=False,
            verdict="",
            finding_count=0,
            raw_line="",
            position_warning="",
            word_count=0,
            is_shallow=True,
        )

    # Strip ANSI escape codes from the entire output
    cleaned = _ANSI_ESCAPE.sub("", doc_master_output)

    # Calculate word count for shallow-output detection
    word_count = len(doc_master_output.split())
    is_shallow = word_count < MIN_DOC_VERDICT_WORDS

    # Split into lines and find all verdict lines
    lines = cleaned.splitlines()
    verdict_matches: list[tuple[int, str, re.Match[str]]] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        match = _VERDICT_PATTERN.match(stripped)
        if match:
            verdict_matches.append((i, stripped, match))

    if not verdict_matches:
        return DocVerdictResult(
            found=False,
            verdict="",
            finding_count=0,
            raw_line="",
            position_warning="",
            word_count=word_count,
            is_shallow=is_shallow,
        )

    # Use the last verdict found
    last_index, raw_line, match = verdict_matches[-1]

    # Determine verdict and finding_count
    verdict_str = match.group(1)  # "PASS" or "FAIL" or "FAIL(N)"
    if verdict_str == "PASS":
        verdict = "PASS"
        finding_count = 0
    elif verdict_str.startswith("FAIL"):
        count_str = match.group(2)  # The content inside parentheses, or None
        if count_str is None:
            # Plain "FAIL" without parentheses
            verdict = "FAIL"
            finding_count = -1
        elif count_str == "0":
            # FAIL(0) is treated as PASS
            verdict = "PASS"
            finding_count = 0
        else:
            try:
                finding_count = int(count_str)
                verdict = "FAIL"
            except ValueError:
                # Non-numeric like FAIL(abc)
                verdict = "FAIL"
                finding_count = -1
    else:
        verdict = ""
        finding_count = -1

    # Check if the verdict is the last non-empty line
    position_warning = ""
    last_nonempty_index = -1
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip():
            last_nonempty_index = i
            break

    if last_nonempty_index != last_index:
        position_warning = (
            f"DOC-DRIFT-VERDICT found at line {last_index + 1} but last "
            f"non-empty line is {last_nonempty_index + 1}. "
            f"Verdict MUST be the very last line of doc-master output."
        )

    return DocVerdictResult(
        found=True,
        verdict=verdict,
        finding_count=finding_count,
        raw_line=raw_line,
        position_warning=position_warning,
        word_count=word_count,
        is_shallow=is_shallow,
    )
