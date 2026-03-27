"""Reviewer effectiveness benchmark library.

Loads labeled datasets of real diffs with ground-truth verdicts,
constructs reviewer prompts, parses model verdicts, and computes
scoring metrics (balanced accuracy, FPR, FNR, consistency).

GitHub Issue: #567
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class BenchmarkSample:
    """A single labeled diff sample for reviewer benchmarking.

    Args:
        sample_id: Unique identifier for this sample
        source_repo: Repository the sample originated from
        issue_ref: Issue reference (e.g., '#538')
        diff_text: Unified diff text
        expected_verdict: Ground-truth verdict (BLOCKING, REQUEST_CHANGES, APPROVE)
        expected_categories: List of expected defect categories
        category_tags: Descriptive tags for the sample
        description: Human-readable description of the defect/change
        difficulty: Difficulty tier for stratification (easy, medium, hard)
        commit_sha: Git commit SHA for provenance tracking
        defect_category: Primary defect category from taxonomy
    """

    sample_id: str
    source_repo: str
    issue_ref: str
    diff_text: str
    expected_verdict: str
    expected_categories: List[str]
    category_tags: List[str]
    description: str
    difficulty: str = "medium"
    commit_sha: str = ""
    defect_category: str = ""


@dataclass
class BenchmarkResult:
    """Result from a single benchmark trial.

    Args:
        sample_id: Which sample was evaluated
        predicted_verdict: The model's verdict
        expected_verdict: Ground-truth verdict
        findings: Parsed findings from the model response
        raw_response: Full model response text
        trial_index: Which trial number (0-indexed)
    """

    sample_id: str
    predicted_verdict: str
    expected_verdict: str
    findings: List[Dict[str, Any]]
    raw_response: str
    trial_index: int


@dataclass
class ScoringReport:
    """Aggregate scoring report from a benchmark run.

    Args:
        balanced_accuracy: (TPR + TNR) / 2
        false_positive_rate: FP / (FP + TN)
        false_negative_rate: FN / (FN + TP)
        per_category: Accuracy breakdown by category tag
        confusion_matrix: Dict with keys TP, TN, FP, FN
        total_samples: Number of unique samples
        trials_per_sample: Number of trials run per sample
        consistency_rate: Average fraction of trials matching majority verdict
        per_difficulty: Accuracy breakdown by difficulty tier (easy, medium, hard)
        per_defect_category: Accuracy breakdown by defect category from taxonomy
        timestamp: When the scoring was computed
    """

    balanced_accuracy: float
    false_positive_rate: float
    false_negative_rate: float
    per_category: Dict[str, Dict[str, Any]]
    confusion_matrix: Dict[str, int]
    total_samples: int
    trials_per_sample: int
    consistency_rate: float
    per_difficulty: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    per_defect_category: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_VALID_VERDICTS = {"BLOCKING", "REQUEST_CHANGES", "APPROVE"}

# Verdicts that count as "defective" (positive class)
_POSITIVE_VERDICTS = {"BLOCKING", "REQUEST_CHANGES"}

# Regex patterns for verdict extraction
_VERDICT_HEADING_RE = re.compile(
    r"##\s*Verdict\s*:\s*(APPROVE|REQUEST_CHANGES|BLOCKING)",
    re.IGNORECASE,
)
_VERDICT_BARE_RE = re.compile(
    r"\b(APPROVE|REQUEST_CHANGES|BLOCKING)\b",
)


def load_dataset(path: Path) -> List[BenchmarkSample]:
    """Load and validate a benchmark dataset from JSON.

    Args:
        path: Path to the dataset JSON file

    Returns:
        List of validated BenchmarkSample instances

    Raises:
        FileNotFoundError: If the dataset file does not exist
        ValueError: If the dataset is invalid (missing fields, bad verdicts, empty)
    """
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")

    data = json.loads(path.read_text())
    samples_raw = data.get("samples", [])

    if not samples_raw:
        raise ValueError(f"Dataset is empty: {path}")

    required_fields = {
        "sample_id", "source_repo", "issue_ref", "diff_text",
        "expected_verdict", "expected_categories", "category_tags", "description",
    }

    samples: List[BenchmarkSample] = []
    for i, s in enumerate(samples_raw):
        missing = required_fields - set(s.keys())
        if missing:
            raise ValueError(
                f"Sample {i} missing required fields: {sorted(missing)}\n"
                f"Sample ID: {s.get('sample_id', '<unknown>')}"
            )

        verdict = s["expected_verdict"]
        if verdict not in _VALID_VERDICTS:
            raise ValueError(
                f"Sample {s['sample_id']} has invalid verdict: {verdict!r}\n"
                f"Valid verdicts: {sorted(_VALID_VERDICTS)}"
            )

        samples.append(BenchmarkSample(
            sample_id=s["sample_id"],
            source_repo=s["source_repo"],
            issue_ref=s["issue_ref"],
            diff_text=s["diff_text"],
            expected_verdict=s["expected_verdict"],
            expected_categories=s["expected_categories"],
            category_tags=s["category_tags"],
            description=s["description"],
            difficulty=s.get("difficulty", "medium"),
            commit_sha=s.get("commit_sha", ""),
            defect_category=s.get("defect_category", ""),
        ))

    return samples


def build_reviewer_prompt(
    sample: BenchmarkSample,
    reviewer_instructions: str,
) -> str:
    """Construct a reviewer prompt from a sample and reviewer instructions.

    Args:
        sample: The benchmark sample containing the diff
        reviewer_instructions: The reviewer agent's system instructions

    Returns:
        Complete prompt string for the model
    """
    return (
        f"{reviewer_instructions}\n\n"
        f"---\n\n"
        f"## Code Review Request\n\n"
        f"**Repository**: {sample.source_repo}\n"
        f"**Issue**: {sample.issue_ref}\n"
        f"**Description**: {sample.description}\n\n"
        f"### Diff\n\n"
        f"```diff\n{sample.diff_text}\n```\n\n"
        f"Please review this diff and provide your verdict "
        f"(APPROVE, REQUEST_CHANGES, or BLOCKING) with findings.\n"
        f"Format your verdict as: ## Verdict: <VERDICT>"
    )


def parse_verdict(response: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Extract verdict and findings from a reviewer model response.

    Looks for '## Verdict: VERDICT' pattern first, then falls back
    to searching the last 200 characters for a bare verdict keyword.

    Args:
        response: The full model response text

    Returns:
        Tuple of (verdict_string, findings_list).
        verdict_string is 'PARSE_ERROR' if no verdict found.
        findings_list contains dicts with 'description' keys extracted
        from the response.
    """
    if not response or not response.strip():
        return "PARSE_ERROR", []

    # Try heading pattern first
    match = _VERDICT_HEADING_RE.search(response)
    if match:
        verdict = match.group(1).upper()
        findings = _extract_findings(response)
        return verdict, findings

    # Fallback: search last 200 chars for bare verdict
    tail = response[-200:] if len(response) > 200 else response
    match = _VERDICT_BARE_RE.search(tail)
    if match:
        verdict = match.group(1).upper()
        findings = _extract_findings(response)
        return verdict, findings

    return "PARSE_ERROR", []


def _extract_findings(response: str) -> List[Dict[str, Any]]:
    """Extract findings from a reviewer response.

    Looks for markdown list items (- or *) that appear to be findings.

    Args:
        response: The model's response text

    Returns:
        List of dicts with 'description' key
    """
    findings: List[Dict[str, Any]] = []
    finding_re = re.compile(r"^\s*[-*]\s+\*?\*?(.+?)(?:\*?\*?\s*$)", re.MULTILINE)
    for m in finding_re.finditer(response):
        text = m.group(1).strip()
        if len(text) > 10:  # Filter noise
            findings.append({"description": text})
    return findings


def _is_positive(verdict: str) -> bool:
    """Check if a verdict is a 'positive' (defective) classification."""
    return verdict in _POSITIVE_VERDICTS


def score_results(
    results: List[BenchmarkResult],
    *,
    samples: Optional[List[BenchmarkSample]] = None,
) -> ScoringReport:
    """Compute scoring metrics from benchmark results.

    Binary classification: BLOCKING/REQUEST_CHANGES = positive (defective),
    APPROVE = negative (clean). PARSE_ERROR results are excluded from
    accuracy calculations but counted in consistency.

    Args:
        results: List of BenchmarkResult from all trials
        samples: Optional list of BenchmarkSample for per-difficulty and
            per-defect-category breakdowns. When provided, builds a lookup
            dict by sample_id to enrich results with metadata.

    Returns:
        ScoringReport with balanced accuracy, FPR, FNR, confusion matrix, etc.
    """
    if not results:
        return ScoringReport(
            balanced_accuracy=0.0,
            false_positive_rate=0.0,
            false_negative_rate=0.0,
            per_category={},
            confusion_matrix={"TP": 0, "TN": 0, "FP": 0, "FN": 0},
            total_samples=0,
            trials_per_sample=0,
            consistency_rate=0.0,
        )

    # Compute confusion matrix (exclude PARSE_ERROR from accuracy)
    tp = tn = fp = fn = 0
    for r in results:
        if r.predicted_verdict == "PARSE_ERROR":
            continue
        actual_positive = _is_positive(r.expected_verdict)
        predicted_positive = _is_positive(r.predicted_verdict)

        if actual_positive and predicted_positive:
            tp += 1
        elif actual_positive and not predicted_positive:
            fn += 1
        elif not actual_positive and predicted_positive:
            fp += 1
        else:
            tn += 1

    # Balanced accuracy = (TPR + TNR) / 2
    tpr = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    tnr = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    balanced_accuracy = (tpr + tnr) / 2.0

    # False positive rate = FP / (FP + TN)
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    # False negative rate = FN / (FN + TP)
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0

    # Per-category accuracy
    per_category = _compute_per_category(results)

    # Consistency rate
    consistency_rate = _compute_consistency(results)

    # Determine unique samples and trials per sample
    sample_ids = {r.sample_id for r in results}
    total_samples = len(sample_ids)
    trials_per_sample = len(results) // total_samples if total_samples > 0 else 0

    # Build sample lookup for difficulty/category breakdowns
    sample_lookup: Dict[str, BenchmarkSample] = {}
    if samples:
        sample_lookup = {s.sample_id: s for s in samples}

    per_difficulty = _compute_per_difficulty(results, sample_lookup)
    per_defect_category = _compute_per_defect_category(results, sample_lookup)

    return ScoringReport(
        balanced_accuracy=balanced_accuracy,
        false_positive_rate=fpr,
        false_negative_rate=fnr,
        per_category=per_category,
        confusion_matrix={"TP": tp, "TN": tn, "FP": fp, "FN": fn},
        total_samples=total_samples,
        trials_per_sample=trials_per_sample,
        consistency_rate=consistency_rate,
        per_difficulty=per_difficulty,
        per_defect_category=per_defect_category,
    )


def _compute_per_difficulty(
    results: List[BenchmarkResult],
    sample_lookup: Dict[str, "BenchmarkSample"],
) -> Dict[str, Dict[str, Any]]:
    """Compute accuracy breakdown by difficulty tier.

    Args:
        results: All benchmark results
        sample_lookup: Mapping of sample_id to BenchmarkSample

    Returns:
        Dict mapping difficulty tier to accuracy stats
    """
    if not sample_lookup:
        return {}

    by_difficulty: Dict[str, List[bool]] = {}
    for r in results:
        if r.predicted_verdict == "PARSE_ERROR":
            continue
        sample = sample_lookup.get(r.sample_id)
        if not sample:
            continue
        difficulty = sample.difficulty or "medium"
        correct = _is_positive(r.predicted_verdict) == _is_positive(r.expected_verdict)
        by_difficulty.setdefault(difficulty, []).append(correct)

    result: Dict[str, Dict[str, Any]] = {}
    for tier, correct_list in by_difficulty.items():
        total = len(correct_list)
        correct_count = sum(correct_list)
        result[tier] = {
            "accuracy": correct_count / total if total > 0 else 0.0,
            "total": total,
            "correct": correct_count,
        }
    return result


def _compute_per_defect_category(
    results: List[BenchmarkResult],
    sample_lookup: Dict[str, "BenchmarkSample"],
) -> Dict[str, Dict[str, Any]]:
    """Compute accuracy breakdown by defect category.

    Args:
        results: All benchmark results
        sample_lookup: Mapping of sample_id to BenchmarkSample

    Returns:
        Dict mapping defect category to accuracy stats
    """
    if not sample_lookup:
        return {}

    by_category: Dict[str, List[bool]] = {}
    for r in results:
        if r.predicted_verdict == "PARSE_ERROR":
            continue
        sample = sample_lookup.get(r.sample_id)
        if not sample or not sample.defect_category:
            continue
        correct = _is_positive(r.predicted_verdict) == _is_positive(r.expected_verdict)
        by_category.setdefault(sample.defect_category, []).append(correct)

    result: Dict[str, Dict[str, Any]] = {}
    for cat, correct_list in by_category.items():
        total = len(correct_list)
        correct_count = sum(correct_list)
        result[cat] = {
            "accuracy": correct_count / total if total > 0 else 0.0,
            "total": total,
            "correct": correct_count,
        }
    return result


def _compute_per_category(results: List[BenchmarkResult]) -> Dict[str, Dict[str, Any]]:
    """Compute per-category accuracy from results.

    Groups by expected_verdict category.

    Args:
        results: All benchmark results

    Returns:
        Dict mapping category to accuracy stats
    """
    categories: Dict[str, List[bool]] = {}
    for r in results:
        if r.predicted_verdict == "PARSE_ERROR":
            continue
        cat = r.expected_verdict
        correct = (
            _is_positive(r.predicted_verdict) == _is_positive(r.expected_verdict)
        )
        categories.setdefault(cat, []).append(correct)

    per_cat: Dict[str, Dict[str, Any]] = {}
    for cat, correct_list in categories.items():
        total = len(correct_list)
        correct_count = sum(correct_list)
        per_cat[cat] = {
            "accuracy": correct_count / total if total > 0 else 0.0,
            "total": total,
            "correct": correct_count,
        }
    return per_cat


def _compute_consistency(results: List[BenchmarkResult]) -> float:
    """Compute consistency rate across trials.

    For each sample, find the majority verdict across trials.
    Consistency for that sample = fraction of trials matching majority.
    Overall consistency = average across all samples.

    Args:
        results: All benchmark results

    Returns:
        Average consistency rate (0.0 to 1.0)
    """
    by_sample: Dict[str, List[str]] = {}
    for r in results:
        by_sample.setdefault(r.sample_id, []).append(r.predicted_verdict)

    if not by_sample:
        return 0.0

    consistencies: List[float] = []
    for verdicts in by_sample.values():
        if not verdicts:
            continue
        counter = Counter(verdicts)
        majority_count = counter.most_common(1)[0][1]
        consistencies.append(majority_count / len(verdicts))

    return sum(consistencies) / len(consistencies) if consistencies else 0.0


def store_benchmark_run(store: Any, report: ScoringReport) -> None:
    """Persist a benchmark report to a BenchmarkStore.

    Stores under the key 'reviewer-effectiveness' with the report's metrics.

    Args:
        store: A BenchmarkStore instance (from skill_evaluator)
        report: The scoring report to persist
    """
    store.update_baseline(
        "reviewer-effectiveness",
        score=report.balanced_accuracy,
        metadata={
            "false_positive_rate": report.false_positive_rate,
            "false_negative_rate": report.false_negative_rate,
            "confusion_matrix": report.confusion_matrix,
            "total_samples": report.total_samples,
            "trials_per_sample": report.trials_per_sample,
            "consistency_rate": report.consistency_rate,
            "per_category": report.per_category,
            "per_difficulty": report.per_difficulty,
            "per_defect_category": report.per_defect_category,
            "timestamp": report.timestamp,
        },
    )
    store.save()
