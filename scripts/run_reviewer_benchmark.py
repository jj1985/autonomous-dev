#!/usr/bin/env python3
"""CLI runner for reviewer effectiveness benchmark.

Runs benchmark samples against an Anthropic model, scores results,
and persists the report.

Usage:
    python scripts/run_reviewer_benchmark.py \
        --dataset tests/benchmarks/reviewer/dataset.json \
        --trials 5 \
        --model claude-sonnet-4-20250514 \
        --output tests/benchmarks/reviewer/results/ \
        --store tests/benchmarks/reviewer/benchmark_results.json

GitHub Issue: #567
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add lib to path
_LIB_DIR = Path(__file__).resolve().parents[1] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(_LIB_DIR))

from reviewer_benchmark import (
    BenchmarkResult,
    ScoringReport,
    build_reviewer_prompt,
    load_dataset,
    parse_verdict,
    score_results,
    store_benchmark_run,
)


def _call_anthropic(
    prompt: str,
    *,
    model: str,
    api_key: str,
    max_tokens: int = 4096,
) -> str:
    """Call the Anthropic API and return the response text.

    Args:
        prompt: The full prompt to send
        model: Model identifier
        api_key: Anthropic API key
        max_tokens: Maximum tokens in response

    Returns:
        Model response text, or empty string on failure
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        print(
            "ERROR: anthropic package not installed.\n"
            "Install with: pip install anthropic",
            file=sys.stderr,
        )
        sys.exit(1)

    client = Anthropic(api_key=api_key)
    try:
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        print(f"WARNING: API call failed: {e}", file=sys.stderr)
        return ""


def main() -> None:
    """Run the reviewer effectiveness benchmark."""
    parser = argparse.ArgumentParser(
        description="Run reviewer effectiveness benchmark against Anthropic API"
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Path to benchmark dataset JSON",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=5,
        help="Number of trials per sample (default: 5)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-20250514",
        help="Anthropic model to use",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Directory to save detailed results JSON",
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help="Path to BenchmarkStore JSON for persistence",
    )
    parser.add_argument(
        "--reviewer-instructions",
        type=Path,
        default=None,
        help="Path to reviewer agent markdown (default: auto-detect)",
    )

    args = parser.parse_args()

    # Validate API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "ERROR: ANTHROPIC_API_KEY environment variable is not set.\n"
            "Set it with: export ANTHROPIC_API_KEY=your-key-here",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load dataset
    print(f"Loading dataset from {args.dataset}...")
    samples = load_dataset(args.dataset)
    print(f"Loaded {len(samples)} samples")

    # Load reviewer instructions
    reviewer_path = args.reviewer_instructions
    if reviewer_path is None:
        reviewer_path = (
            Path(__file__).resolve().parents[1]
            / "plugins"
            / "autonomous-dev"
            / "agents"
            / "reviewer.md"
        )
    if reviewer_path.exists():
        reviewer_instructions = reviewer_path.read_text()
        print(f"Loaded reviewer instructions from {reviewer_path}")
    else:
        reviewer_instructions = "You are a code reviewer. Review the diff and provide a verdict."
        print(f"WARNING: Reviewer instructions not found at {reviewer_path}, using default")

    # Run benchmark
    results: list[BenchmarkResult] = []
    total_calls = len(samples) * args.trials
    call_num = 0

    for sample in samples:
        for trial in range(args.trials):
            call_num += 1
            print(
                f"  [{call_num}/{total_calls}] {sample.sample_id} trial {trial + 1}...",
                end=" ",
                flush=True,
            )

            prompt = build_reviewer_prompt(sample, reviewer_instructions)
            response = _call_anthropic(prompt, model=args.model, api_key=api_key)

            verdict, findings = parse_verdict(response)

            results.append(BenchmarkResult(
                sample_id=sample.sample_id,
                predicted_verdict=verdict,
                expected_verdict=sample.expected_verdict,
                findings=findings,
                raw_response=response,
                trial_index=trial,
            ))

            status = "OK" if verdict != "PARSE_ERROR" else "PARSE_ERROR"
            match_str = "MATCH" if verdict == sample.expected_verdict else "MISMATCH"
            print(f"{verdict} ({match_str}) [{status}]")

            # Brief delay between calls to avoid rate limits
            if call_num < total_calls:
                time.sleep(0.5)

    # Score results
    print("\nScoring results...")
    report = score_results(results)

    # Print summary
    print("\n" + "=" * 60)
    print("REVIEWER EFFECTIVENESS BENCHMARK REPORT")
    print("=" * 60)
    print(f"Model:              {args.model}")
    print(f"Total samples:      {report.total_samples}")
    print(f"Trials per sample:  {report.trials_per_sample}")
    print(f"Balanced accuracy:  {report.balanced_accuracy:.3f}")
    print(f"False positive rate: {report.false_positive_rate:.3f}")
    print(f"False negative rate: {report.false_negative_rate:.3f}")
    print(f"Consistency rate:   {report.consistency_rate:.3f}")
    print(f"\nConfusion matrix:")
    for k, v in report.confusion_matrix.items():
        print(f"  {k}: {v}")
    if report.per_category:
        print(f"\nPer-category accuracy:")
        for cat, stats in report.per_category.items():
            print(f"  {cat}: {stats['accuracy']:.3f} ({stats['correct']}/{stats['total']})")
    print("=" * 60)

    # Save detailed results
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        output_file = args.output / f"benchmark_{ts}.json"
        detail = {
            "model": args.model,
            "trials": args.trials,
            "dataset": str(args.dataset),
            "timestamp": report.timestamp,
            "report": {
                "balanced_accuracy": report.balanced_accuracy,
                "false_positive_rate": report.false_positive_rate,
                "false_negative_rate": report.false_negative_rate,
                "consistency_rate": report.consistency_rate,
                "confusion_matrix": report.confusion_matrix,
                "per_category": report.per_category,
                "total_samples": report.total_samples,
                "trials_per_sample": report.trials_per_sample,
            },
            "results": [
                {
                    "sample_id": r.sample_id,
                    "predicted_verdict": r.predicted_verdict,
                    "expected_verdict": r.expected_verdict,
                    "findings": r.findings,
                    "trial_index": r.trial_index,
                    "raw_response_length": len(r.raw_response),
                }
                for r in results
            ],
        }
        output_file.write_text(json.dumps(detail, indent=2))
        print(f"\nDetailed results saved to: {output_file}")

    # Store in BenchmarkStore
    if args.store:
        try:
            from skill_evaluator import BenchmarkStore

            store = BenchmarkStore(args.store)
            store.load()
            store_benchmark_run(store, report)
            print(f"Report stored in: {args.store}")
        except ImportError:
            print(
                "WARNING: Could not import BenchmarkStore. "
                "Results not persisted to store.",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
