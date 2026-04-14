"""Prompt quality anti-pattern rules for agent prompts (Issue #842).

Shared library used by:
- tests/unit/test_prompt_quality.py (static inspection)
- unified_pre_tool.py Layer 6 (write-time validation)
"""
import re
from typing import List

# Persona pattern: catches "You are an expert", "You are a world-class",
# but NOT "You are the **implementer** agent" (legitimate role assignment).
PERSONA_PATTERN = re.compile(
    r"(?i)(?:^|\n)\s*you are (?:an? )?(?:expert|senior|world[- ]class|renowned|leading|top)"
)

# Casual register phrases that weaken enforcement prompts.
CASUAL_REGISTER_PATTERNS = [
    re.compile(r"(?i)\bcheck for\b"),
    re.compile(r"(?i)\blook for\b"),
    re.compile(r"(?i)\bmake sure\b"),
    re.compile(r"(?i)\btry to\b"),
    re.compile(r"(?i)\byou should\b"),
    re.compile(r"(?i)\bfeel free\b"),
]

# Maximum bullet items per ## section before flagging as oversized.
CONSTRAINT_DENSITY_THRESHOLD = 8


def check_persona(content: str) -> List[str]:
    """Check for banned persona patterns.

    Catches opener phrases like "You are an expert" or "You are a senior"
    which are anti-patterns in enforcement prompts.  Legitimate role
    assignments like "You are the **implementer** agent" are allowed.

    Args:
        content: Full text content to check.

    Returns:
        List of violation descriptions (empty if no violations).
    """
    violations: List[str] = []
    for match in PERSONA_PATTERN.finditer(content):
        line_num = content[:match.start()].count("\n") + 1
        matched_text = match.group().strip()
        violations.append(
            f"Line {line_num}: Banned persona opener '{matched_text}'. "
            f"Use role assignment (e.g. 'You are the **agent** agent') instead."
        )
    return violations


def check_casual_register(content: str) -> List[str]:
    """Check for casual register phrases.

    Phrases like 'make sure', 'try to', 'feel free' weaken enforcement.
    Use 'MUST', 'REQUIRED', 'FORBIDDEN' instead.

    Args:
        content: Full text content to check.

    Returns:
        List of violation descriptions with line numbers.
    """
    violations: List[str] = []
    for pattern in CASUAL_REGISTER_PATTERNS:
        for match in pattern.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            matched_text = match.group().strip()
            violations.append(
                f"Line {line_num}: Casual register phrase '{matched_text}'. "
                f"Use formal directive language (MUST, REQUIRED, FORBIDDEN) instead."
            )
    return violations


def check_constraint_density(
    content: str, threshold: int = CONSTRAINT_DENSITY_THRESHOLD
) -> List[str]:
    """Check for oversized constraint sections.

    Counts bullet items (lines starting with - or *) per ## section.
    Sections exceeding the threshold are flagged.

    Args:
        content: Full text content to check.
        threshold: Maximum allowed bullet items per section.

    Returns:
        List of violation descriptions (empty if no violations).
    """
    violations: List[str] = []
    lines = content.split("\n")

    current_section: str = "(top-level)"
    section_start_line: int = 1
    bullet_count: int = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Detect ## section headers (not # or ###)
        if stripped.startswith("## ") and not stripped.startswith("### "):
            # Check previous section before moving to next
            if bullet_count > threshold:
                violations.append(
                    f"Section '{current_section}' (line {section_start_line}): "
                    f"{bullet_count} bullet items exceeds threshold of {threshold}."
                )
            current_section = stripped.lstrip("# ").strip()
            section_start_line = i + 1
            bullet_count = 0
        elif stripped.startswith("- ") or stripped.startswith("* "):
            bullet_count += 1

    # Check final section
    if bullet_count > threshold:
        violations.append(
            f"Section '{current_section}' (line {section_start_line}): "
            f"{bullet_count} bullet items exceeds threshold of {threshold}."
        )

    return violations


def check_all(content: str) -> List[str]:
    """Run all prompt quality checks.

    Args:
        content: Full text content to check.

    Returns:
        Combined list of violations from all checks (empty = pass).
    """
    violations: List[str] = []
    violations.extend(check_persona(content))
    violations.extend(check_casual_register(content))
    violations.extend(check_constraint_density(content))
    return violations
