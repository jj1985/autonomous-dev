#!/usr/bin/env python3
"""Skill Change Detector - Detect skill modifications and check eval readiness.

Provides functions to identify which skills were modified in a set of changed
files, check whether those skills have evaluation prompts and baselines, and
format results for pipeline output.

Used by STEP 11.5 (Skill Effectiveness Gate) in the /implement pipeline and
by /improve for weak-skill reporting.

Issue: #643
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


# Pattern matches paths like skills/testing-guide/SKILL.md or
# plugins/autonomous-dev/skills/my-skill/SKILL.md
_SKILL_PATH_PATTERN = re.compile(r"(?:^|/)skills/([^/]+)/SKILL\.md$")


def detect_skill_changes(file_paths: List[str]) -> List[str]:
    """Extract skill names from file paths matching skills/*/SKILL.md.

    Args:
        file_paths: List of file paths (relative or absolute) from git diff or similar.

    Returns:
        Deduplicated, sorted list of skill names that were modified.
    """
    skills: set[str] = set()
    for path in file_paths:
        match = _SKILL_PATH_PATTERN.search(path)
        if match:
            skills.add(match.group(1))
    return sorted(skills)


def get_eval_status(skill_name: str, *, repo_root: Path) -> Dict:
    """Check if a skill has eval prompts and baseline data.

    Args:
        skill_name: Name of the skill (e.g. "testing-guide").
        repo_root: Path to the repository root.

    Returns:
        Dict with keys: skill_name, has_eval_prompts, baseline, evaluable.
    """
    eval_prompts_path = repo_root / "tests" / "genai" / "skills" / "eval_prompts" / f"{skill_name}.json"
    baselines_path = repo_root / "tests" / "genai" / "skills" / "baselines" / "effectiveness.json"

    has_eval_prompts = eval_prompts_path.is_file()

    baseline: Optional[Dict] = None
    if baselines_path.is_file():
        try:
            data = json.loads(baselines_path.read_text(encoding="utf-8"))
            if skill_name in data:
                entry = data[skill_name]
                baseline = {
                    "pass_rate_with": entry.get("pass_rate_with", 0.0),
                    "delta": entry.get("delta", 0.0),
                    "recorded": entry.get("recorded", ""),
                }
        except (json.JSONDecodeError, KeyError, TypeError):
            baseline = None

    return {
        "skill_name": skill_name,
        "has_eval_prompts": has_eval_prompts,
        "baseline": baseline,
        "evaluable": has_eval_prompts,
    }


def format_skill_eval_report(results: List[Dict]) -> str:
    """Format skill evaluation results for pipeline output.

    Args:
        results: List of dicts from get_eval_status, optionally augmented
                 with a "run_result" key containing eval run output.

    Returns:
        Formatted multi-line string for pipeline display.
    """
    if not results:
        return "No skill changes detected."

    lines: List[str] = []
    lines.append("SKILL EFFECTIVENESS GATE")
    lines.append("=" * 40)

    has_block = False

    for r in results:
        name = r["skill_name"]
        if not r["has_eval_prompts"]:
            lines.append(f"  WARNING: Skill '{name}' modified but has no eval prompts")
            continue

        baseline = r.get("baseline")
        if baseline is None:
            lines.append(f"  PASS: Skill '{name}' has eval prompts (no baseline yet)")
            continue

        delta = baseline.get("delta", 0.0)
        pass_rate = baseline.get("pass_rate_with", 0.0)

        if delta < -0.10:
            lines.append(
                f"  BLOCK: Skill '{name}' delta={delta:+.2f} "
                f"(pass_rate={pass_rate:.2f}) — regression detected"
            )
            has_block = True
        else:
            lines.append(
                f"  PASS: Skill '{name}' delta={delta:+.2f} "
                f"(pass_rate={pass_rate:.2f})"
            )

    lines.append("=" * 40)
    verdict = "BLOCKED" if has_block else "PASS"
    lines.append(f"VERDICT: {verdict}")

    return "\n".join(lines)


def get_weak_skills(
    baselines_path: Path,
    *,
    min_delta: float = 0.10,
    min_pass_rate: float = 0.80,
    stale_days: int = 30,
) -> List[Dict]:
    """Identify weak, low-quality, or stale skills from baselines file.

    Used by /improve to surface skills needing attention.

    Args:
        baselines_path: Path to effectiveness.json baselines file.
        min_delta: Minimum acceptable delta (skills below are "weak").
        min_pass_rate: Minimum acceptable pass rate (skills below are "low quality").
        stale_days: Number of days after which a baseline is considered stale.

    Returns:
        List of dicts with keys: skill_name, reason, pass_rate_with, delta, recorded.
    """
    if not baselines_path.is_file():
        return []

    try:
        data = json.loads(baselines_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError):
        return []

    now = datetime.now(timezone.utc)
    weak: List[Dict] = []

    for skill_name, entry in data.items():
        if not isinstance(entry, dict):
            continue

        pass_rate = entry.get("pass_rate_with", 0.0)
        delta = entry.get("delta", 0.0)
        recorded = entry.get("recorded", "")

        reasons: List[str] = []

        if delta < min_delta:
            reasons.append(f"weak delta ({delta:+.2f} < {min_delta:+.2f})")

        if pass_rate < min_pass_rate:
            reasons.append(f"low pass rate ({pass_rate:.2f} < {min_pass_rate:.2f})")

        if recorded:
            try:
                recorded_dt = datetime.fromisoformat(recorded.replace("Z", "+00:00"))
                if recorded_dt.tzinfo is None:
                    recorded_dt = recorded_dt.replace(tzinfo=timezone.utc)
                age = (now - recorded_dt).days
                if age > stale_days:
                    reasons.append(f"stale baseline ({age} days old)")
            except (ValueError, TypeError):
                reasons.append("unparseable recorded date")

        if reasons:
            weak.append({
                "skill_name": skill_name,
                "reason": "; ".join(reasons),
                "pass_rate_with": pass_rate,
                "delta": delta,
                "recorded": recorded,
            })

    return sorted(weak, key=lambda x: x["delta"])
