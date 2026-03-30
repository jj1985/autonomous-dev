"""GenAI UAT: Skill effectiveness harness.

Measures whether injecting a skill into context actually improves output quality.
Not "is the skill well-written?" (test_skill_evals.py covers that) but "does it work?"

For each skill, generates code WITH and WITHOUT the skill injected, then uses
binary criteria to measure the delta. Skills that don't measurably improve
output are flagged — they consume context tokens for zero behavioral change.

Requires --genai flag. Use --update-baselines to record new baseline scores.

Usage:
    pytest tests/genai/skills/test_skill_effectiveness.py --genai
    pytest tests/genai/skills/test_skill_effectiveness.py --genai --update-baselines
    pytest tests/genai/skills/test_skill_effectiveness.py --genai -k "python_standards"
"""

import json
from datetime import date
from pathlib import Path

import pytest

from ..conftest import PROJECT_ROOT

pytestmark = [pytest.mark.genai]

PLUGIN_ROOT = PROJECT_ROOT / "plugins" / "autonomous-dev"
EVAL_PROMPTS_DIR = Path(__file__).parent / "eval_prompts"
BASELINES_FILE = Path(__file__).parent / "baselines" / "effectiveness.json"

# Skills with eval prompts defined — add to this list as you create new eval_prompts/*.json
EVALUATED_SKILLS = [
    "python-standards",
    "security-patterns",
    "testing-guide",
    "architecture-patterns",
    "error-handling",
]

# Minimum delta to consider a skill "effective" — skill must improve criteria
# pass rate by at least this much, OR achieve this absolute pass rate
MIN_DELTA = 0.10
MIN_ABSOLUTE_PASS_RATE = 0.80

# Maximum allowed regression from recorded baseline
MAX_REGRESSION = 0.15


def pytest_addoption(parser):
    """Add --update-baselines flag."""
    try:
        parser.addoption(
            "--update-baselines",
            action="store_true",
            default=False,
            help="Update baseline effectiveness scores after test run",
        )
    except ValueError:
        pass  # Option already added


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_eval_prompts(skill_name: str) -> dict:
    """Load eval prompts for a skill, skip if none defined."""
    prompt_file = EVAL_PROMPTS_DIR / f"{skill_name}.json"
    if not prompt_file.exists():
        pytest.skip(f"No eval prompts defined for {skill_name}")
    return json.loads(prompt_file.read_text())


def _load_skill(skill_name: str) -> str:
    """Load skill markdown content, skip if not found."""
    skill_file = PLUGIN_ROOT / "skills" / skill_name / "SKILL.md"
    if not skill_file.exists():
        pytest.skip(f"Skill {skill_name} not found at {skill_file}")
    return skill_file.read_text()


def _load_baselines() -> dict:
    """Load recorded baseline scores."""
    if not BASELINES_FILE.exists():
        return {}
    data = json.loads(BASELINES_FILE.read_text())
    # Filter out metadata keys
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _save_baselines(baselines: dict) -> None:
    """Save baseline scores with metadata."""
    output = {
        "_comment": "Baseline effectiveness scores per skill. Updated by test_skill_effectiveness.py --update-baselines.",
        "_updated": str(date.today()),
    }
    output.update(baselines)
    BASELINES_FILE.write_text(json.dumps(output, indent=2) + "\n")


def _judge_binary(genai, response: str, criterion: str) -> bool:
    """Binary judge: does the response satisfy this specific criterion?

    Uses a strict binary threshold (score >= 7 out of 10) to convert
    the LLM judge's rating into a yes/no answer.
    """
    result = genai.judge(
        question=f"Does this code output satisfy the following criterion: {criterion}",
        context=f"Generated code output:\n```\n{response[:3000]}\n```",
        criteria=(
            f"Evaluate strictly whether the output satisfies: '{criterion}'. "
            f"Score 10 = clearly and unambiguously satisfies the criterion. "
            f"Score 5 = partially or ambiguously satisfies it. "
            f"Score 0 = clearly does not satisfy it. "
            f"Be strict — if you have to squint to see it, score low."
        ),
    )
    return result.get("score", 0) >= 7


def _evaluate_skill(genai, skill_name: str, max_prompts: int = 5) -> dict:
    """Compute effectiveness delta for one skill.

    Generates outputs WITH and WITHOUT the skill injected, then judges
    each output against the skill's binary criteria.

    Args:
        genai: GenAI client instance
        skill_name: Name of skill to evaluate
        max_prompts: Maximum prompts to evaluate (controls cost)

    Returns:
        dict with pass rates, delta, and per-prompt details
    """
    eval_config = _load_eval_prompts(skill_name)
    skill_content = _load_skill(skill_name)

    # Strip frontmatter from skill for injection
    content_lines = skill_content.split("\n")
    if content_lines[0].strip() == "---":
        end_idx = next(
            (i for i in range(1, len(content_lines)) if content_lines[i].strip() == "---"),
            0,
        )
        skill_body = "\n".join(content_lines[end_idx + 1 :]).strip()
    else:
        skill_body = skill_content

    prompts = eval_config["prompts"][:max_prompts]
    results = []

    for prompt_config in prompts:
        task = prompt_config["task"]
        criteria = prompt_config["criteria"]

        # Generate WITHOUT skill
        response_without = genai.ask(
            prompt=f"Complete this task. Write production-quality code.\n\nTask: {task}",
            system="You are a senior software engineer. Write clean, production-ready code.",
            max_tokens=2048,
        )

        # Generate WITH skill injected
        response_with = genai.ask(
            prompt=f"Complete this task. Write production-quality code.\n\nTask: {task}",
            system=(
                f"You are a senior software engineer. Follow these guidelines strictly:\n\n"
                f"{skill_body[:4000]}\n\n"
                f"Write clean, production-ready code that follows the above guidelines."
            ),
            max_tokens=2048,
        )

        # Judge both outputs against each criterion
        score_without = sum(1 for c in criteria if _judge_binary(genai, response_without, c))
        score_with = sum(1 for c in criteria if _judge_binary(genai, response_with, c))

        results.append(
            {
                "task": task[:100],
                "criteria_count": len(criteria),
                "score_without": score_without,
                "score_with": score_with,
                "delta": score_with - score_without,
            }
        )

    total_without = sum(r["score_without"] for r in results)
    total_with = sum(r["score_with"] for r in results)
    total_criteria = sum(r["criteria_count"] for r in results)

    return {
        "skill": skill_name,
        "prompts_tested": len(results),
        "total_criteria": total_criteria,
        "pass_rate_without": total_without / total_criteria if total_criteria else 0,
        "pass_rate_with": total_with / total_criteria if total_criteria else 0,
        "delta": (total_with - total_without) / total_criteria if total_criteria else 0,
        "details": results,
    }


def _format_result(result: dict) -> str:
    """Format an effectiveness result for assertion messages."""
    return (
        f"{result['skill']}: "
        f"without={result['pass_rate_without']:.0%}, "
        f"with={result['pass_rate_with']:.0%}, "
        f"delta={result['delta']:+.0%} "
        f"({result['prompts_tested']} prompts, {result['total_criteria']} criteria)"
    )


# ---------------------------------------------------------------------------
# Tests: Per-Skill Effectiveness
# ---------------------------------------------------------------------------


class TestSkillEffectiveness:
    """Measure whether each skill actually improves output quality."""

    @pytest.mark.parametrize("skill_name", EVALUATED_SKILLS)
    def test_skill_improves_output(self, genai, skill_name, request):
        """Skill injection should measurably improve criteria pass rate.

        Asserts EITHER:
        - The skill improves pass rate by >= MIN_DELTA (10%), OR
        - The skill achieves >= MIN_ABSOLUTE_PASS_RATE (80%) with injection

        The second condition handles the case where the base model already
        scores well — the skill may not improve much, but if the combined
        output is excellent, the skill isn't harmful.
        """
        result = _evaluate_skill(genai, skill_name, max_prompts=5)

        # Store result for baseline update
        if not hasattr(request.config, "_effectiveness_results"):
            request.config._effectiveness_results = {}
        request.config._effectiveness_results[skill_name] = result

        # Skill should not make things WORSE
        assert result["delta"] >= -0.1, (
            f"Skill DEGRADES output quality!\n{_format_result(result)}\n"
            f"The skill is making outputs worse — review the skill content."
        )

        # Skill should provide measurable improvement OR achieve high absolute rate
        effective = result["delta"] >= MIN_DELTA or result["pass_rate_with"] >= MIN_ABSOLUTE_PASS_RATE
        assert effective, (
            f"Skill shows no measurable improvement:\n{_format_result(result)}\n"
            f"Required: delta >= {MIN_DELTA:.0%} OR pass_rate_with >= {MIN_ABSOLUTE_PASS_RATE:.0%}\n"
            f"Either the skill isn't teaching anything new, or the base model "
            f"already knows this domain well enough. Consider:\n"
            f"  1. Adding more specific/actionable guidance to the skill\n"
            f"  2. Targeting areas where the base model is weakest\n"
            f"  3. Dropping the skill if it adds no value"
        )


# ---------------------------------------------------------------------------
# Tests: Regression Against Baselines
# ---------------------------------------------------------------------------


class TestSkillRegression:
    """Verify no skill has regressed below its recorded baseline."""

    @pytest.mark.parametrize("skill_name", EVALUATED_SKILLS)
    def test_no_regression_from_baseline(self, genai, skill_name, request):
        """Skill should not drop more than MAX_REGRESSION below its baseline.

        Skips if no baseline recorded for this skill.
        """
        baselines = _load_baselines()
        if skill_name not in baselines:
            pytest.skip(f"No baseline recorded for {skill_name} — run with --update-baselines first")

        baseline = baselines[skill_name]
        result = _evaluate_skill(genai, skill_name, max_prompts=3)

        # Store for potential baseline update
        if not hasattr(request.config, "_effectiveness_results"):
            request.config._effectiveness_results = {}
        request.config._effectiveness_results[skill_name] = result

        baseline_rate = baseline["pass_rate_with"]
        current_rate = result["pass_rate_with"]
        regression = baseline_rate - current_rate

        assert regression <= MAX_REGRESSION, (
            f"Skill REGRESSED from baseline!\n"
            f"  Baseline: {baseline_rate:.0%} (recorded {baseline.get('recorded', 'unknown')})\n"
            f"  Current:  {current_rate:.0%}\n"
            f"  Regression: {regression:.0%} (max allowed: {MAX_REGRESSION:.0%})\n"
            f"The skill or the eval model may have changed. Investigate before updating baseline."
        )


# ---------------------------------------------------------------------------
# Tests: Cross-Skill Degradation Check
# ---------------------------------------------------------------------------


class TestNoDegradation:
    """Quick check that no skill makes output actively worse."""

    def test_no_skill_degrades_output(self, genai):
        """Spot-check all skills with eval prompts — none should degrade output.

        Uses only 2 prompts per skill for cost efficiency. This is a smoke
        test, not a comprehensive evaluation.
        """
        degraded = []

        for skill_name in EVALUATED_SKILLS:
            try:
                result = _evaluate_skill(genai, skill_name, max_prompts=2)
            except Exception as e:
                # Don't fail the whole test on one skill's eval error
                degraded.append(f"{skill_name}: eval error — {e}")
                continue

            if result["delta"] < -0.15:
                degraded.append(
                    f"{skill_name}: delta={result['delta']:+.0%} "
                    f"(without={result['pass_rate_without']:.0%}, "
                    f"with={result['pass_rate_with']:.0%})"
                )

        assert not degraded, "Skills that degrade output quality:\n" + "\n".join(f"  - {d}" for d in degraded)


# ---------------------------------------------------------------------------
# Tests: Effectiveness Report
# ---------------------------------------------------------------------------


class TestEffectivenessReport:
    """Generate a summary report of skill effectiveness."""

    def test_generate_report(self, genai, request):
        """Run all skills and produce a ranked effectiveness report.

        This test always passes — it's for reporting, not gating.
        Use --update-baselines to persist results.
        """
        report_lines = ["Skill Effectiveness Report", "=" * 60]
        all_results = {}

        for skill_name in EVALUATED_SKILLS:
            try:
                result = _evaluate_skill(genai, skill_name, max_prompts=3)
                all_results[skill_name] = result
                report_lines.append(
                    f"  {skill_name:30s} | "
                    f"without: {result['pass_rate_without']:5.0%} | "
                    f"with: {result['pass_rate_with']:5.0%} | "
                    f"delta: {result['delta']:+5.0%} | "
                    f"{'OK' if result['delta'] >= MIN_DELTA or result['pass_rate_with'] >= MIN_ABSOLUTE_PASS_RATE else 'WEAK'}"
                )
            except Exception as e:
                report_lines.append(f"  {skill_name:30s} | ERROR: {e}")

        report_lines.append("=" * 60)

        # Sort by delta descending
        ranked = sorted(all_results.items(), key=lambda x: x[1]["delta"], reverse=True)
        if ranked:
            report_lines.append("Ranked by effectiveness:")
            for i, (name, r) in enumerate(ranked, 1):
                report_lines.append(f"  {i}. {name} (delta: {r['delta']:+.0%})")

        # Print report
        report = "\n".join(report_lines)
        print(f"\n{report}")

        # Update baselines if flag set
        update = request.config.getoption("--update-baselines", default=False)
        if update and all_results:
            baselines = _load_baselines()
            for name, result in all_results.items():
                baselines[name] = {
                    "pass_rate_with": round(result["pass_rate_with"], 3),
                    "pass_rate_without": round(result["pass_rate_without"], 3),
                    "delta": round(result["delta"], 3),
                    "prompts_tested": result["prompts_tested"],
                    "recorded": str(date.today()),
                }
            _save_baselines(baselines)
            print(f"\nBaselines updated in {BASELINES_FILE}")


# ---------------------------------------------------------------------------
# Conftest hook: update baselines at end of session if requested
# ---------------------------------------------------------------------------


def pytest_terminal_summary(terminalreporter, config):
    """Print effectiveness summary at end of test run."""
    results = getattr(config, "_effectiveness_results", {})
    if not results:
        return

    terminalreporter.section("Skill Effectiveness Summary")
    for name, result in sorted(results.items()):
        status = "OK" if result["delta"] >= MIN_DELTA or result["pass_rate_with"] >= MIN_ABSOLUTE_PASS_RATE else "WEAK"
        terminalreporter.line(
            f"  {name:30s} | "
            f"delta: {result['delta']:+5.0%} | "
            f"with: {result['pass_rate_with']:5.0%} | "
            f"{status}"
        )
