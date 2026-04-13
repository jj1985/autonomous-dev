"""Plan file validator for the planning workflow system.

Validates plan files contain required sections and checks plan age/expiry.
Used by plan_gate.py hook to enforce plan-before-write workflow.

Part of Issue #814: Planning workflow system.
"""

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Required sections that every plan must contain
REQUIRED_SECTIONS = [
    "## WHY + SCOPE",
    "## Existing Solutions",
    "## Minimal Path",
]

# Plan expiry threshold in hours (plans older than this trigger a warning)
PLAN_EXPIRY_HOURS = 72


@dataclass
class PlanValidationResult:
    """Result of validating a plan file.

    Attributes:
        valid: Whether the plan passes all validation checks.
        missing_sections: List of required sections not found in the plan.
        plan_path: Path to the validated plan file, if any.
        age_hours: Age of the plan file in hours.
        expired: Whether the plan is older than the expiry threshold (warning only).
    """

    valid: bool
    missing_sections: list[str] = field(default_factory=list)
    plan_path: Optional[Path] = None
    age_hours: float = 0.0
    expired: bool = False


def find_latest_plan(plans_dir: Path) -> Optional[Path]:
    """Find the most recent plan file in the plans directory.

    Searches for .md files and returns the newest one by modification time.

    Args:
        plans_dir: Directory to search for plan files.

    Returns:
        Path to the newest plan file, or None if no plans exist.
    """
    if not plans_dir.exists() or not plans_dir.is_dir():
        return None

    plan_files = list(plans_dir.glob("*.md"))
    if not plan_files:
        return None

    # Sort by modification time, newest first
    plan_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return plan_files[0]


def validate_plan(plan_path: Path) -> PlanValidationResult:
    """Validate a plan file against required sections and expiry.

    Checks that the plan contains all required sections (WHY + SCOPE,
    Existing Solutions, Minimal Path) and calculates plan age. Plans
    older than 72 hours are marked as expired with a warning, but
    are NOT blocked -- expired plans warn, they do not block work.

    Args:
        plan_path: Path to the plan file to validate.

    Returns:
        PlanValidationResult with validation details.
    """
    if not plan_path.exists():
        return PlanValidationResult(
            valid=False,
            missing_sections=[s for s in REQUIRED_SECTIONS],
            plan_path=plan_path,
        )

    content = plan_path.read_text()

    # Check for required sections (case-insensitive header matching)
    missing_sections: list[str] = []
    for section in REQUIRED_SECTIONS:
        # Extract the section name without the ## prefix for flexible matching
        section_name = section.lstrip("#").strip()
        # Match as markdown header (## or ###) or as-is
        pattern = rf"#+\s*{re.escape(section_name)}"
        if not re.search(pattern, content, re.IGNORECASE):
            missing_sections.append(section)

    # Calculate plan age
    mtime = plan_path.stat().st_mtime
    age_hours = (time.time() - mtime) / 3600.0

    # Check expiry -- expired plans are warned about, NOT blocked
    is_expired = age_hours > PLAN_EXPIRY_HOURS

    return PlanValidationResult(
        valid=len(missing_sections) == 0,
        missing_sections=missing_sections,
        plan_path=plan_path,
        age_hours=age_hours,
        expired=is_expired,
    )
