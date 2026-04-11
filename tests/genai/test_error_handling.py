"""GenAI UAT: Error handling quality across libs and hooks.

Samples critical Python files and judges error handling practices.
"""

import pytest

from .conftest import PROJECT_ROOT

pytestmark = [pytest.mark.genai]

PLUGIN_ROOT = PROJECT_ROOT / "plugins" / "autonomous-dev"


def _sample_python_files(max_files: int = 10):
    """Sample critical .py files from lib/ and hooks/."""
    files = []
    for subdir in ["lib", "hooks"]:
        d = PLUGIN_ROOT / subdir
        if d.exists():
            for f in sorted(d.glob("*.py")):
                if f.stem != "__init__" and f.stat().st_size > 200:
                    files.append(f)
    # Take up to max_files, prioritizing larger files
    files.sort(key=lambda f: f.stat().st_size, reverse=True)
    return files[:max_files]


class TestErrorHandling:
    def test_error_handling_quality(self, genai):
        """Critical Python files should have quality error handling."""
        files = _sample_python_files(10)
        assert len(files) > 0, "No Python files found to sample"

        samples = []
        for f in files:
            content = f.read_text()[:1500]
            rel = f.relative_to(PLUGIN_ROOT)
            samples.append(f"--- {rel} ---\n{content}")

        result = genai.judge(
            question="Rate the error handling quality of these Python files (1-10)",
            context="\n\n".join(samples)[:8000],
            criteria="Good error handling: try/except around I/O and external calls, "
            "meaningful error messages with context, no bare except, "
            "no silent failures (empty except blocks), proper logging or re-raising. "
            "Score 10 = excellent, 6 = acceptable, 3 = poor.",
        )
        assert result["score"] >= 6, f"Error handling quality too low: {result['reasoning']}"

    def test_no_silent_failures(self, genai):
        """Files should not silently swallow exceptions.

        Detects multiple silent-swallow patterns beyond bare ``except: pass``:
        - ``except:`` with no body or only ``pass``
        - ``except Exception:`` / ``except Exception as e:`` without re-raise or ``exc_info=True``
        - ``contextlib.suppress()`` wrapping operations where failure would be significant
        - ``finally`` blocks containing ``return``/``break``/``continue``
        """
        files = _sample_python_files(10)

        # Detect suspect patterns: bare except, except-pass, except-log-without-raise,
        # contextlib.suppress usage, and finally-with-return/break/continue.
        import re

        _SILENT_SWALLOW_PATTERNS = [
            re.compile(r"except\s*:", re.MULTILINE),
            re.compile(r"except\s+Exception(\s+as\s+\w+)?\s*:\s*\n\s*pass", re.MULTILINE),
            re.compile(r"contextlib\.suppress\(", re.MULTILINE),
            re.compile(r"finally\s*:(?:[^}]*?)\b(return|break|continue)\b", re.MULTILINE | re.DOTALL),
        ]

        suspect_snippets = []
        for f in files:
            content = f.read_text()
            if any(pat.search(content) for pat in _SILENT_SWALLOW_PATTERNS):
                rel = f.relative_to(PLUGIN_ROOT)
                suspect_snippets.append(f"--- {rel} ---\n{content[:1000]}")

        if not suspect_snippets:
            # No suspects found, pass
            return

        result = genai.judge(
            question="Do these files silently swallow exceptions in a harmful way?",
            context="\n\n".join(suspect_snippets)[:6000],
            criteria="Bare except or except-pass is acceptable ONLY for cleanup/fallback code "
            "where failure is non-critical. "
            "except-Exception without re-raise or exc_info=True is a silent swallow. "
            "contextlib.suppress() on non-trivial operations is risky. "
            "finally with return/break/continue suppresses pending exceptions. "
            "Score 10 = all justified, 6 = mostly justified, 3 = dangerous silent failures.",
        )
        assert result["score"] >= 6, f"Silent failure risk: {result['reasoning']}"

    def test_error_handling_analytic(self, genai):
        """Analytic rubric evaluation of error handling practices."""
        files = _sample_python_files(10)
        assert len(files) > 0, "No Python files found to sample"

        import re as _re

        samples = []
        for f in files:
            content = f.read_text()[:1500]
            rel = f.relative_to(PLUGIN_ROOT)
            samples.append(f"--- {rel} ---\n{content}")

        # Detect patterns for context
        has_bare_except = any("except:" in open(f).read() for f in files)
        has_context_msgs = any("f\"" in open(f).read() or "f'" in open(f).read() for f in files)

        context = "\n\n".join(samples)[:8000]

        result = genai.judge_analytic(
            question="Evaluate error handling quality",
            context=context,
            criteria=[
                {
                    "name": "No bare except",
                    "description": "Files do not use bare 'except:' or 'except Exception: pass' "
                    "patterns that silently swallow all errors.",
                    "max_points": 1,
                },
                {
                    "name": "Contextual error messages",
                    "description": "Error messages include context about what went wrong, "
                    "not just generic 'Error occurred' messages.",
                    "max_points": 1,
                },
                {
                    "name": "Try/except around I/O",
                    "description": "File I/O and external calls are wrapped in try/except "
                    "blocks with appropriate error handling.",
                    "max_points": 1,
                },
            ],
        )
        assert result["total_score"] >= 1, (
            f"Error handling analytic: {result['total_score']}/{result['max_score']} - "
            f"{result['reasoning']}"
        )

    def test_no_finally_return_suppression(self, genai):
        """Files should not use return/break/continue inside finally blocks.

        A ``return`` (or ``break``/``continue``) inside a ``finally`` block silently
        discards any exception propagating out of the corresponding ``try`` body.
        This is one of the hardest-to-spot silent-swallow patterns.
        """
        files = _sample_python_files(10)

        import re

        _FINALLY_SUPPRESS_RE = re.compile(
            r"finally\s*:(?:[^}]*?)\b(return|break|continue)\b",
            re.MULTILINE | re.DOTALL,
        )

        suspect_snippets = []
        for f in files:
            content = f.read_text()
            if _FINALLY_SUPPRESS_RE.search(content):
                rel = f.relative_to(PLUGIN_ROOT)
                suspect_snippets.append(f"--- {rel} ---\n{content[:1500]}")

        if not suspect_snippets:
            # No suspects found — pattern absent, nothing to judge
            return

        result = genai.judge(
            question="Do these files use return/break/continue inside finally blocks in a way that suppresses exceptions?",
            context="\n\n".join(suspect_snippets)[:6000],
            criteria="return/break/continue inside a finally block is acceptable ONLY when the code "
            "intentionally overrides exception propagation (rare, must be documented). "
            "Score 10 = all uses are intentional and documented, 6 = mostly justified, "
            "3 = dangerous exception suppression.",
        )
        assert result["score"] >= 6, f"Finally-return suppression risk: {result['reasoning']}"
