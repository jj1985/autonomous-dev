"""Coverage baseline storage and regression detection."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple


def get_default_baseline_path() -> Path:
    """Resolve .claude/local/coverage_baseline.json from repo root, handling worktrees."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        git_path = parent / ".git"
        if git_path.is_dir() or git_path.is_file():
            return parent / ".claude" / "local" / "coverage_baseline.json"
    return cwd / ".claude" / "local" / "coverage_baseline.json"


def load_baseline(baseline_path: Optional[Path] = None) -> dict:
    """Load coverage baseline. Returns empty dict if missing or corrupted."""
    path = baseline_path or get_default_baseline_path()
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_baseline(
    coverage_pct: float,
    skip_count: int,
    total_tests: int,
    baseline_path: Optional[Path] = None,
) -> None:
    """Save coverage baseline."""
    path = baseline_path or get_default_baseline_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "total_coverage": coverage_pct,
        "skip_count": skip_count,
        "total_tests": total_tests,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(data, indent=2))


def check_coverage_regression(
    current_coverage: float,
    tolerance: float = 0.5,
    baseline_path: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Check if coverage regressed from baseline. Returns (passed, message)."""
    baseline = load_baseline(baseline_path)
    if not baseline or "total_coverage" not in baseline:
        return (True, f"Baseline established at {current_coverage:.1f}%")

    baseline_coverage = baseline["total_coverage"]
    threshold = baseline_coverage - tolerance

    if current_coverage >= threshold:
        return (True, f"Coverage maintained: {current_coverage:.1f}% (baseline: {baseline_coverage:.1f}%)")
    else:
        return (False, f"Coverage regression: {current_coverage:.1f}% < {baseline_coverage:.1f}% - {tolerance}% tolerance")


def check_skip_regression(
    current_skipped: int,
    baseline_path: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Check if skip count has increased from baseline.

    Args:
        current_skipped: Current number of skipped tests.
        baseline_path: Path to baseline JSON. Uses default if None.

    Returns:
        Tuple of (passed, message). passed=False if skip count increased.
    """
    baseline = load_baseline(baseline_path)
    if not baseline or "skip_count" not in baseline:
        return (True, "No baseline — skip count established")

    baseline_skip = baseline["skip_count"]
    if current_skipped > baseline_skip:
        return (
            False,
            f"Skip count increased: {current_skipped} > {baseline_skip}. "
            f"0 new skips allowed.",
        )
    return (
        True,
        f"Skip count OK: {current_skipped} (baseline: {baseline_skip})",
    )


def check_test_count_regression(
    current_test_count: int,
    *,
    tolerance_pct: float = 10.0,
    tolerance_abs: int = 20,
    baseline_path: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Check if test count has dropped significantly from baseline.

    Blocks if the test count drops by more than min(tolerance_pct%, tolerance_abs)
    from the stored baseline. This detects test deletion gaming where behavioral
    tests are removed and replaced with fewer structural checks.

    Args:
        current_test_count: Current number of tests in the suite.
        tolerance_pct: Maximum allowed percentage drop (default 10%).
        tolerance_abs: Maximum allowed absolute drop (default 20 tests).
        baseline_path: Path to baseline JSON. Uses default if None.

    Returns:
        Tuple of (passed, message). passed=False if test count dropped beyond tolerance.
    """
    baseline = load_baseline(baseline_path)
    if not baseline or "total_tests" not in baseline:
        return (True, "No baseline — test count established")

    baseline_count = baseline["total_tests"]

    # Division by zero guard: if baseline is 0, any count is fine
    if baseline_count == 0:
        return (True, f"Test count OK: {current_test_count} (baseline was 0)")

    # Calculate allowed drop as min(percentage-based, absolute)
    pct_drop_allowed = baseline_count * (tolerance_pct / 100.0)
    abs_drop_allowed = float(tolerance_abs)
    max_drop = min(pct_drop_allowed, abs_drop_allowed)

    actual_drop = baseline_count - current_test_count

    if actual_drop > max_drop:
        drop_pct = (actual_drop / baseline_count) * 100
        return (
            False,
            f"Test count regression: {current_test_count} < {baseline_count} "
            f"(dropped {actual_drop} tests, {drop_pct:.1f}%). "
            f"Max allowed drop: {max_drop:.0f} tests.",
        )
    return (
        True,
        f"Test count OK: {current_test_count} (baseline: {baseline_count})",
    )


def check_skip_rate(skipped: int, total: int) -> Tuple[str, str]:
    """Check skip rate. Returns (level, message). Level is 'ok', 'warn', or 'block'."""
    if total == 0:
        return ("ok", "No tests found")
    rate = (skipped / total) * 100
    if rate <= 5.0:
        return ("ok", f"Skip rate {rate:.1f}% is acceptable")
    elif rate <= 10.0:
        return ("warn", f"Skip rate {rate:.1f}% exceeds 5% — consider fixing skipped tests")
    else:
        return ("block", f"Skip rate {rate:.1f}% exceeds 10% — must reduce skipped tests before proceeding")
