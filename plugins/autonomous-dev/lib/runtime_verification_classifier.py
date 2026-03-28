"""Runtime verification classifier for the evaluator agent.

Classifies changed files into runtime verification categories (frontend,
API, CLI) so the reviewer can perform targeted runtime checks after
completing static code review.

Usage:
    from runtime_verification_classifier import classify_runtime_targets

    plan = classify_runtime_targets(["src/routes/api.py", "public/index.html"])
    print(plan.has_targets)  # True
    print(plan.summary)      # "Frontend: 1 target(s), API: 1 target(s)"

Date: 2026-03-28
Issue: #564
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import List


@dataclass
class FrontendTarget:
    """A frontend file that can be verified via Playwright or browser."""

    file_path: str
    framework: str  # html, react, vue, svelte
    suggested_checks: List[str] = field(default_factory=list)


@dataclass
class ApiTarget:
    """An API route/endpoint file that can be verified via curl."""

    file_path: str
    framework: str  # fastapi, flask, express, generic
    endpoints: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)


@dataclass
class CliTarget:
    """A CLI tool or script that can be verified via subprocess."""

    file_path: str
    tool_name: str
    suggested_commands: List[str] = field(default_factory=list)


@dataclass
class RuntimeVerificationPlan:
    """Aggregated runtime verification plan for a set of changed files."""

    has_targets: bool
    frontend: List[FrontendTarget] = field(default_factory=list)
    api: List[ApiTarget] = field(default_factory=list)
    cli: List[CliTarget] = field(default_factory=list)
    summary: str = ""


# --- Frontend detection ---

_FRONTEND_EXTENSIONS = {
    ".html": "html",
    ".tsx": "react",
    ".jsx": "react",
    ".vue": "vue",
    ".svelte": "svelte",
}

_FRONTEND_CHECKS = {
    "html": ["Page loads without errors", "Key elements render"],
    "react": ["Component renders", "No console errors"],
    "vue": ["Component mounts", "Reactive data binds"],
    "svelte": ["Component renders", "No hydration errors"],
}


def _detect_frontend_targets(file_paths: List[str]) -> List[FrontendTarget]:
    """Detect frontend files that can be runtime-verified.

    Matches files by extension: .html, .tsx, .jsx, .vue, .svelte.
    Excludes test files.

    Args:
        file_paths: List of file paths to classify.

    Returns:
        List of FrontendTarget objects.
    """
    targets: List[FrontendTarget] = []
    for fpath in file_paths:
        p = PurePosixPath(fpath)
        ext = p.suffix.lower()
        if ext in _FRONTEND_EXTENSIONS:
            if _is_test_file(fpath):
                continue
            framework = _FRONTEND_EXTENSIONS[ext]
            targets.append(
                FrontendTarget(
                    file_path=fpath,
                    framework=framework,
                    suggested_checks=list(_FRONTEND_CHECKS.get(framework, [])),
                )
            )
    return targets


# --- API detection ---

_API_PATH_PATTERNS = [
    re.compile(r"(?:^|/)routes/"),
    re.compile(r"(?:^|/)api/"),
    re.compile(r"(?:^|/)endpoints/"),
    re.compile(r"(?:^|/)views/"),
]

_API_FILENAMES = {"app.py", "main.py", "server.py", "server.js", "server.ts"}

_FRAMEWORK_HINTS = {
    "fastapi": re.compile(r"(?:fastapi|fast_api)", re.IGNORECASE),
    "flask": re.compile(r"flask", re.IGNORECASE),
    "express": re.compile(r"express|\.js$|\.ts$"),
}


def _guess_api_framework(file_path: str) -> str:
    """Guess the API framework from the file path.

    Args:
        file_path: Path to the file.

    Returns:
        Framework name string.
    """
    for framework, pattern in _FRAMEWORK_HINTS.items():
        if pattern.search(file_path):
            return framework
    if file_path.endswith((".js", ".ts")):
        return "express"
    if file_path.endswith(".py"):
        return "generic"
    return "generic"


def _detect_api_targets(file_paths: List[str]) -> List[ApiTarget]:
    """Detect API route/endpoint files that can be runtime-verified.

    Matches files in routes/, api/, endpoints/, views/ directories,
    or named app.py, main.py, server.py, etc.

    Excludes test files and markdown files.

    Args:
        file_paths: List of file paths to classify.

    Returns:
        List of ApiTarget objects.
    """
    targets: List[ApiTarget] = []
    for fpath in file_paths:
        if _is_test_file(fpath):
            continue
        if fpath.endswith(".md"):
            continue

        p = PurePosixPath(fpath)
        is_api = False

        for pattern in _API_PATH_PATTERNS:
            if pattern.search(fpath):
                is_api = True
                break

        if not is_api and p.name in _API_FILENAMES:
            is_api = True

        if is_api:
            framework = _guess_api_framework(fpath)
            targets.append(
                ApiTarget(
                    file_path=fpath,
                    framework=framework,
                    endpoints=[],
                    methods=["GET"],
                )
            )
    return targets


# --- CLI detection ---

_CLI_DIR_PATTERNS = [
    re.compile(r"(?:^|/)bin/"),
    re.compile(r"(?:^|/)cli/"),
    re.compile(r"(?:^|/)scripts/"),
]

_CLI_FILE_PATTERNS = [
    re.compile(r"_cli\.py$"),
    re.compile(r"^cli_.*\.py$"),
    re.compile(r"\.sh$"),
]

_CLI_EXCLUSION_PATTERNS = [
    re.compile(r"(?:^|/)plugins/[^/]+/commands/"),
    re.compile(r"(?:^|/)plugins/[^/]+/agents/"),
    re.compile(r"(?:^|/)commands/[^/]+\.md$"),
    re.compile(r"(?:^|/)agents/[^/]+\.md$"),
    re.compile(r"\.md$"),
]


def _detect_cli_targets(file_paths: List[str]) -> List[CliTarget]:
    """Detect CLI tools and scripts that can be runtime-verified.

    Matches .sh files, files in bin/, cli/, scripts/ directories,
    and files named *_cli.py or cli_*.py.

    Excludes this project's Markdown commands/agents and test files.

    Args:
        file_paths: List of file paths to classify.

    Returns:
        List of CliTarget objects.
    """
    targets: List[CliTarget] = []
    for fpath in file_paths:
        if _is_test_file(fpath):
            continue

        excluded = False
        for pattern in _CLI_EXCLUSION_PATTERNS:
            if pattern.search(fpath):
                excluded = True
                break
        if excluded:
            continue

        p = PurePosixPath(fpath)
        is_cli = False

        for pattern in _CLI_DIR_PATTERNS:
            if pattern.search(fpath):
                is_cli = True
                break

        if not is_cli:
            for pattern in _CLI_FILE_PATTERNS:
                if pattern.search(p.name):
                    is_cli = True
                    break

        if is_cli:
            tool_name = p.stem
            suggested = _build_cli_suggestions(fpath, tool_name)
            targets.append(
                CliTarget(
                    file_path=fpath,
                    tool_name=tool_name,
                    suggested_commands=suggested,
                )
            )
    return targets


def _build_cli_suggestions(file_path: str, tool_name: str) -> List[str]:
    """Build suggested verification commands for a CLI target.

    Args:
        file_path: Path to the CLI file.
        tool_name: Name of the tool (stem).

    Returns:
        List of suggested shell commands.
    """
    if file_path.endswith(".sh"):
        return [f"timeout 30 bash {file_path} --help"]
    if file_path.endswith(".py"):
        return [f"timeout 30 python3 {file_path} --help"]
    return [f"timeout 30 ./{file_path} --version"]


def _is_test_file(file_path: str) -> bool:
    """Check if a file path looks like a test file.

    Args:
        file_path: Path to check.

    Returns:
        True if the file appears to be a test file.
    """
    p = PurePosixPath(file_path)
    name = p.name.lower()
    if name.startswith("test_") or name.endswith("_test.py") or name.endswith(".test.tsx"):
        return True
    if name.endswith(".test.js") or name.endswith(".test.ts") or name.endswith(".spec.ts"):
        return True
    parts = p.parts
    for part in parts:
        if part in ("tests", "test", "__tests__", "spec"):
            return True
    return False


def _build_summary(
    frontend: List[FrontendTarget],
    api: List[ApiTarget],
    cli: List[CliTarget],
) -> str:
    """Build a human-readable summary of the verification plan.

    Args:
        frontend: Frontend targets.
        api: API targets.
        cli: CLI targets.

    Returns:
        Summary string.
    """
    parts: List[str] = []
    if frontend:
        parts.append(f"Frontend: {len(frontend)} target(s)")
    if api:
        parts.append(f"API: {len(api)} target(s)")
    if cli:
        parts.append(f"CLI: {len(cli)} target(s)")
    if not parts:
        return "No runtime verification targets detected"
    return ", ".join(parts)


def classify_runtime_targets(file_paths: List[str]) -> RuntimeVerificationPlan:
    """Classify changed files into runtime verification categories.

    Main entry point for the runtime verification classifier. Analyzes
    file paths and determines which can be verified at runtime via
    Playwright (frontend), curl (API), or subprocess (CLI).

    Args:
        file_paths: List of changed file paths to classify.

    Returns:
        RuntimeVerificationPlan with categorized targets and summary.

    Example:
        >>> plan = classify_runtime_targets(["src/App.tsx", "api/routes/users.py"])
        >>> plan.has_targets
        True
        >>> len(plan.frontend)
        1
        >>> len(plan.api)
        1
    """
    frontend = _detect_frontend_targets(file_paths)
    api = _detect_api_targets(file_paths)
    cli = _detect_cli_targets(file_paths)

    has_targets = bool(frontend or api or cli)
    summary = _build_summary(frontend, api, cli)

    return RuntimeVerificationPlan(
        has_targets=has_targets,
        frontend=frontend,
        api=api,
        cli=cli,
        summary=summary,
    )
