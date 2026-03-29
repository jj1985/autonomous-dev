"""
Detect file-write operations in Python code snippets.

Uses AST-based extraction with regex fallback for when AST parsing fails.
Designed to detect bypass attempts in Bash commands like:
    python3 -c "from pathlib import Path as P; P('agents/foo.md').write_text('x')"

Issue #589: Addresses gaps in aliased imports, shutil operations, and eval/exec indirection.
"""

import ast
import re
from typing import List

# Sentinel returned when eval()/exec() with non-constant args is detected
SUSPICIOUS_EXEC_SENTINEL = "__SUSPICIOUS_EXEC__"

# Maximum snippet length to prevent DoS via huge code strings
MAX_SNIPPET_LENGTH = 10_000

# --- AST-based detection ---


class _WriteTargetVisitor(ast.NodeVisitor):
    """AST visitor that extracts file paths from write operations.

    Detects:
    - Path(...).write_text(...) / write_bytes(...) with any alias
    - open(path, 'w'/'a'/'wb'/'ab') calls
    - shutil.copy/copy2/move destination arguments
    - eval()/exec() with non-constant arguments (suspicious)
    """

    def __init__(self) -> None:
        self.targets: List[str] = []
        self._path_aliases: set[str] = {"Path"}  # Track Path class aliases
        self._shutil_aliases: set[str] = {"shutil"}  # Track shutil module aliases
        self._has_suspicious_exec: bool = False

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Track 'from pathlib import Path as P' style aliases."""
        if node.module and "pathlib" in node.module:
            for alias in (node.names or []):
                if alias.name == "Path":
                    self._path_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Track 'import shutil as s' style aliases."""
        for alias in (node.names or []):
            if alias.name == "shutil":
                self._shutil_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Detect write operations in function calls."""
        self._check_path_write(node)
        self._check_open_write(node)
        self._check_shutil_write(node)
        self._check_exec_eval(node)
        self.generic_visit(node)

    def _check_path_write(self, node: ast.Call) -> None:
        """Detect Path(...).write_text(...) / write_bytes(...)."""
        func = node.func
        if not isinstance(func, ast.Attribute):
            return
        if func.attr not in ("write_text", "write_bytes"):
            return

        # The value should be a Call to Path (or alias)
        value = func.value
        if isinstance(value, ast.Call):
            call_name = self._get_call_name(value)
            if call_name in self._path_aliases:
                path_arg = self._extract_string_arg(value, 0)
                if path_arg:
                    self.targets.append(path_arg)

    def _check_open_write(self, node: ast.Call) -> None:
        """Detect open(path, 'w'/'a'/'wb'/'ab') calls."""
        call_name = self._get_call_name(node)
        if call_name != "open":
            return

        # Need at least 2 args: path and mode
        mode = self._extract_string_arg(node, 1)
        if mode is None:
            # Check keyword argument 'mode'
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode = str(kw.value.value)
                    break

        if mode and any(c in mode for c in ("w", "a")):
            path_arg = self._extract_string_arg(node, 0)
            if path_arg:
                self.targets.append(path_arg)

    def _check_shutil_write(self, node: ast.Call) -> None:
        """Detect shutil.copy/copy2/move destination arguments."""
        func = node.func
        if not isinstance(func, ast.Attribute):
            return
        if func.attr not in ("copy", "copy2", "move", "copyfile"):
            return

        # Check if the object is shutil (or alias)
        obj_name = self._get_node_name(func.value)
        if obj_name not in self._shutil_aliases:
            return

        # Destination is the second positional argument
        dst = self._extract_string_arg(node, 1)
        if dst:
            self.targets.append(dst)

    def _check_exec_eval(self, node: ast.Call) -> None:
        """Detect eval()/exec() with non-constant arguments."""
        call_name = self._get_call_name(node)
        if call_name not in ("eval", "exec"):
            return

        # If the first argument is a constant string, recursively parse it
        # to detect writes hidden inside exec("Path('agents/x').write_text('y')")
        if node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                inner_targets = extract_write_targets_ast_safe(first_arg.value)
                if inner_targets:
                    self.targets.extend(inner_targets)
                return  # Handled: either found targets or truly safe

        # Non-constant argument: suspicious
        self._has_suspicious_exec = True

    def _get_call_name(self, node: ast.Call) -> str:
        """Get the simple name of a function call."""
        return self._get_node_name(node.func)

    def _get_node_name(self, node: ast.AST) -> str:
        """Get simple name from a Name or Attribute node."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""

    def _extract_string_arg(self, node: ast.Call, index: int) -> "str | None":
        """Extract a string constant from a positional argument."""
        if index < len(node.args):
            arg = node.args[index]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return arg.value
        return None


def extract_write_targets_ast(code: str) -> List[str]:
    """Extract file-write targets from Python code using AST parsing.

    Args:
        code: Python code snippet to analyze.

    Returns:
        List of file paths that would be written to. May include
        SUSPICIOUS_EXEC_SENTINEL if eval/exec with dynamic args is found.

    Raises:
        SyntaxError: If the code cannot be parsed.
        RecursionError: If the AST is too deeply nested.
        MemoryError: If the code is too large.
    """
    tree = ast.parse(code, mode="exec")
    visitor = _WriteTargetVisitor()
    visitor.visit(tree)

    targets = list(visitor.targets)
    if visitor._has_suspicious_exec:
        targets.append(SUSPICIOUS_EXEC_SENTINEL)
    return targets


def extract_write_targets_ast_safe(code: str) -> List[str]:
    """Like extract_write_targets_ast but returns empty list on parse failure.

    Used for recursively parsing constant strings inside exec/eval calls.

    Args:
        code: Python code snippet to analyze.

    Returns:
        List of file paths that would be written to (empty on parse failure).
    """
    try:
        return extract_write_targets_ast(code)
    except (SyntaxError, RecursionError, MemoryError, ValueError, TypeError):
        return []


# --- Regex-based fallback detection ---

# Patterns for Path(...).write_text/write_bytes with any alias
_REGEX_PATH_WRITE = re.compile(
    r"""(?:\w+)\s*\(\s*['"]([^'"]+)['"]\s*\)\.write_(?:text|bytes)""",
    re.VERBOSE,
)

# Patterns for open(path, 'w'/'a') calls
_REGEX_OPEN_WRITE = re.compile(
    r"""open\s*\(\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]*)['"]\s*\)""",
    re.VERBOSE,
)

# Patterns for shutil.copy/copy2/move/copyfile
_REGEX_SHUTIL_WRITE = re.compile(
    r"""(?:\w+)\.(?:copy|copy2|move|copyfile)\s*\(\s*['"][^'"]*['"]\s*,\s*['"]([^'"]+)['"]""",
    re.VERBOSE,
)

# Patterns for eval/exec with non-string arguments
_REGEX_SUSPICIOUS_EXEC = re.compile(
    r"""\b(?:eval|exec)\s*\(\s*(?!['"])""",
    re.VERBOSE,
)


def extract_write_targets_regex(code: str) -> List[str]:
    """Extract file-write targets from Python code using regex (fallback).

    Less accurate than AST but works on syntactically invalid snippets.

    Args:
        code: Python code snippet to analyze.

    Returns:
        List of file paths that would be written to.
    """
    targets: List[str] = []

    # Path(...).write_text/write_bytes
    for match in _REGEX_PATH_WRITE.finditer(code):
        targets.append(match.group(1))

    # open(path, 'w'/'a')
    for match in _REGEX_OPEN_WRITE.finditer(code):
        mode = match.group(2)
        if any(c in mode for c in ("w", "a")):
            targets.append(match.group(1))

    # shutil operations
    for match in _REGEX_SHUTIL_WRITE.finditer(code):
        targets.append(match.group(1))

    # Suspicious exec/eval
    if _REGEX_SUSPICIOUS_EXEC.search(code):
        targets.append(SUSPICIOUS_EXEC_SENTINEL)

    return targets


# --- Combined API ---


def _preprocess_snippet(code: str) -> str:
    """Pre-process a code snippet for AST parsing.

    Replaces literal escape sequences (from shell -c strings) with actual
    characters so AST can parse multiline code.

    Args:
        code: Raw code snippet, possibly with literal \\n and \\t.

    Returns:
        Pre-processed code string.
    """
    if len(code) > MAX_SNIPPET_LENGTH:
        code = code[:MAX_SNIPPET_LENGTH]

    # Replace literal \n and \t (from shell -c strings) with actual characters
    # Only replace \n that isn't \\n (escaped backslash)
    code = code.replace("\\n", "\n").replace("\\t", "\t")
    return code


def extract_write_targets(code: str) -> List[str]:
    """Extract file-write targets from Python code (AST with regex fallback).

    This is the main entry point. Tries AST parsing first for accuracy,
    falls back to regex if AST fails.

    Args:
        code: Python code snippet to analyze.

    Returns:
        List of file paths that would be written to. May include
        SUSPICIOUS_EXEC_SENTINEL if suspicious eval/exec is found.
    """
    if not code or not code.strip():
        return []

    processed = _preprocess_snippet(code)

    try:
        return extract_write_targets_ast(processed)
    except (SyntaxError, RecursionError, MemoryError, ValueError, TypeError):
        return extract_write_targets_regex(processed)


def has_suspicious_exec(code: str) -> bool:
    """Quick check for eval/exec with dynamic (non-constant) arguments.

    Args:
        code: Python code snippet to analyze.

    Returns:
        True if suspicious eval/exec is found.
    """
    targets = extract_write_targets(code)
    return SUSPICIOUS_EXEC_SENTINEL in targets
