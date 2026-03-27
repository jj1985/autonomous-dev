#!/usr/bin/env python3
"""Mine git repositories for reviewer benchmark samples.

Scans fix commits and clean commits to generate labeled diff samples
for the reviewer effectiveness benchmark dataset.

Usage:
    python scripts/mine_git_samples.py \
        --repo-path /path/to/repo \
        --since 2025-01-01 \
        --output candidates.json \
        --max-samples 50

GitHub Issue: #573
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# Load taxonomy for classification
_TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "tests" / "benchmarks" / "reviewer" / "taxonomy.json"


def _load_taxonomy() -> Dict[str, Any]:
    """Load the defect taxonomy from taxonomy.json.

    Returns:
        Parsed taxonomy dict, or empty dict if file not found.
    """
    if _TAXONOMY_PATH.exists():
        return json.loads(_TAXONOMY_PATH.read_text())
    return {}


# Keyword-to-category mapping for commit message classification
_KEYWORD_CATEGORIES: Dict[str, str] = {
    "hardcoded": "hardcoded-value",
    "hardcode": "hardcoded-value",
    "magic number": "hardcoded-value",
    "dispatch": "wrong-dispatch",
    "routing": "wrong-dispatch",
    "null": "null-safety",
    "none": "null-safety",
    "nullable": "null-safety",
    "npe": "null-safety",
    "stub": "stub-implementation",
    "not implemented": "stub-implementation",
    "notimplementederror": "stub-implementation",
    "orphan": "orphan-reference",
    "dangling": "orphan-reference",
    "unused import": "orphan-reference",
    "incomplete": "incomplete-fix",
    "partial fix": "incomplete-fix",
    "off-by-one": "off-by-one",
    "off by one": "off-by-one",
    "fencepost": "off-by-one",
    "default": "wrong-default",
    "wrong default": "wrong-default",
    "security": "removed-security",
    "bypass": "bypass-alternative-path",
    "skip": "test-skip-abuse",
    "race condition": "race-condition",
    "race": "race-condition",
    "deadlock": "race-condition",
    "cache": "stale-cache",
    "stale": "stale-cache",
    "secret": "secrets-committed",
    "api key": "secrets-committed",
    "token": "secrets-committed",
    "swallow": "error-swallowed",
    "silent": "silent-import-fail",
    "division by zero": "division-by-zero",
    "divide by zero": "division-by-zero",
    "zerodivision": "division-by-zero",
}


def classify_defect(diff_text: str, commit_msg: str) -> str:
    """Classify a defect based on diff content and commit message.

    Matches keywords in the commit message and diff text against known
    defect categories from the taxonomy.

    Args:
        diff_text: The unified diff text
        commit_msg: The commit message

    Returns:
        Defect category string, or empty string if unclassified.
    """
    combined = (commit_msg + " " + diff_text).lower()
    for keyword, category in _KEYWORD_CATEGORIES.items():
        if keyword in combined:
            return category
    return ""


def estimate_difficulty(
    diff_text: str,
    num_files: int,
    defect_category: str,
) -> str:
    """Estimate the difficulty of detecting a defect in a diff.

    Heuristic based on diff size, number of files, and defect type.

    Args:
        diff_text: The unified diff text
        num_files: Number of files changed in the diff
        defect_category: The classified defect category

    Returns:
        Difficulty tier: 'easy', 'medium', or 'hard'.
    """
    # Easy categories (obvious patterns)
    easy_categories = {
        "stub-implementation", "hardcoded-value", "secrets-committed",
        "test-skip-abuse", "api-endpoint-501",
    }
    # Hard categories (subtle patterns)
    hard_categories = {
        "race-condition", "stale-cache", "non-atomic-update",
        "incomplete-fix", "test-passes-without-fix", "coverage-gamed",
        "bypass-alternative-path",
    }

    if defect_category in easy_categories:
        return "easy"
    if defect_category in hard_categories:
        return "hard"

    # Size-based heuristic
    lines = diff_text.count("\n")
    if lines < 10 and num_files == 1:
        return "easy"
    if lines > 30 or num_files > 2:
        return "hard"
    return "medium"


def extract_diff(repo_path: str, commit_sha: str) -> str:
    """Extract the unified diff for a given commit.

    Args:
        repo_path: Path to the git repository
        commit_sha: Git commit SHA

    Returns:
        Unified diff text as a string.

    Raises:
        subprocess.CalledProcessError: If git command fails.
    """
    result = subprocess.run(
        ["git", "diff", f"{commit_sha}~1", commit_sha, "--unified=3"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def mine_fix_commits(
    repo_path: str,
    *,
    since: str = "2025-01-01",
) -> List[Dict[str, Any]]:
    """Mine fix/bugfix commits from a git repository.

    Searches for commits with 'fix' in the message and extracts
    their diffs as candidate defective samples.

    Args:
        repo_path: Path to the git repository
        since: ISO date string to start searching from

    Returns:
        List of candidate sample dicts.
    """
    result = subprocess.run(
        [
            "git", "log", f"--since={since}",
            "--grep=fix", "-i",
            "--format=%H|%s",
            "--no-merges",
        ],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )

    candidates: List[Dict[str, Any]] = []
    repo_name = Path(repo_path).name

    for line in result.stdout.strip().split("\n"):
        if not line or "|" not in line:
            continue
        sha, msg = line.split("|", 1)
        sha = sha.strip()
        msg = msg.strip()

        try:
            diff = extract_diff(repo_path, sha)
        except subprocess.CalledProcessError:
            continue

        if not diff or len(diff) < 20:
            continue

        # Count files changed
        num_files = diff.count("diff --git")
        defect_cat = classify_defect(diff, msg)
        difficulty = estimate_difficulty(diff, num_files, defect_cat)

        candidates.append({
            "sample_id": f"{repo_name}-{sha[:8]}-fix",
            "source_repo": repo_name,
            "issue_ref": "",
            "commit_sha": sha,
            "description": msg,
            "diff_text": diff[:2000],  # Truncate very large diffs
            "expected_verdict": "BLOCKING",
            "expected_categories": [defect_cat] if defect_cat else [],
            "category_tags": [defect_cat] if defect_cat else ["functionality"],
            "difficulty": difficulty,
            "defect_category": defect_cat,
        })

    return candidates


def mine_clean_commits(
    repo_path: str,
    *,
    since: str = "2025-01-01",
) -> List[Dict[str, Any]]:
    """Mine clean (non-fix) commits from a git repository.

    Searches for commits that add features, refactor, or update docs
    as candidate APPROVE samples.

    Args:
        repo_path: Path to the git repository
        since: ISO date string to start searching from

    Returns:
        List of candidate clean sample dicts.
    """
    result = subprocess.run(
        [
            "git", "log", f"--since={since}",
            "--grep=feat\\|refactor\\|docs\\|chore", "-i",
            "--format=%H|%s",
            "--no-merges",
        ],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )

    candidates: List[Dict[str, Any]] = []
    repo_name = Path(repo_path).name

    for line in result.stdout.strip().split("\n"):
        if not line or "|" not in line:
            continue
        sha, msg = line.split("|", 1)
        sha = sha.strip()
        msg = msg.strip()

        # Skip if it's actually a fix
        if "fix" in msg.lower():
            continue

        try:
            diff = extract_diff(repo_path, sha)
        except subprocess.CalledProcessError:
            continue

        if not diff or len(diff) < 20:
            continue

        candidates.append({
            "sample_id": f"{repo_name}-{sha[:8]}-clean",
            "source_repo": repo_name,
            "issue_ref": "",
            "commit_sha": sha,
            "description": msg,
            "diff_text": diff[:2000],
            "expected_verdict": "APPROVE",
            "expected_categories": [],
            "category_tags": ["refactor"],
            "difficulty": "easy",
            "defect_category": "",
        })

    return candidates


def build_sample(
    sample_id: str,
    source_repo: str,
    diff_text: str,
    description: str,
    *,
    expected_verdict: str = "BLOCKING",
    issue_ref: str = "",
    commit_sha: str = "",
    expected_categories: Optional[List[str]] = None,
    category_tags: Optional[List[str]] = None,
    difficulty: str = "medium",
    defect_category: str = "",
) -> Dict[str, Any]:
    """Build a single benchmark sample dict.

    Args:
        sample_id: Unique identifier
        source_repo: Repository name
        diff_text: Unified diff text
        description: Human-readable description
        expected_verdict: Ground truth verdict
        issue_ref: Issue reference
        commit_sha: Commit SHA
        expected_categories: Expected defect categories
        category_tags: Descriptive tags
        difficulty: Difficulty tier
        defect_category: Primary defect category

    Returns:
        Sample dict compatible with dataset.json format.
    """
    return {
        "sample_id": sample_id,
        "source_repo": source_repo,
        "issue_ref": issue_ref,
        "commit_sha": commit_sha,
        "diff_text": diff_text,
        "expected_verdict": expected_verdict,
        "expected_categories": expected_categories or [],
        "category_tags": category_tags or [],
        "description": description,
        "difficulty": difficulty,
        "defect_category": defect_category,
    }


def main() -> None:
    """Run the git sample mining CLI."""
    parser = argparse.ArgumentParser(
        description="Mine git repositories for reviewer benchmark samples"
    )
    parser.add_argument(
        "--repo-path",
        type=str,
        action="append",
        required=True,
        help="Path to git repository (repeatable)",
    )
    parser.add_argument(
        "--since",
        type=str,
        default="2025-01-01",
        help="Start date for commit search (default: 2025-01-01)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=100,
        help="Maximum number of samples to output (default: 100)",
    )

    args = parser.parse_args()

    all_candidates: List[Dict[str, Any]] = []

    for repo_path in args.repo_path:
        print(f"Mining fix commits from {repo_path}...", file=sys.stderr)
        fix_samples = mine_fix_commits(repo_path, since=args.since)
        all_candidates.extend(fix_samples)

        print(f"Mining clean commits from {repo_path}...", file=sys.stderr)
        clean_samples = mine_clean_commits(repo_path, since=args.since)
        all_candidates.extend(clean_samples)

    # Truncate to max samples
    if len(all_candidates) > args.max_samples:
        all_candidates = all_candidates[: args.max_samples]

    print(f"Found {len(all_candidates)} candidate samples", file=sys.stderr)

    output = json.dumps(all_candidates, indent=2)
    if args.output:
        args.output.write_text(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
