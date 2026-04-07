"""Covers Index — Pre-computed source-path to doc-file mapping for doc-master.

Parses `covers:` YAML frontmatter from docs/*.md files and builds a lookup
index. Eliminates doc-master's per-invocation 23-file scan (Issue #713).

Usage:
    from covers_index import build_covers_index, get_affected_docs, save_covers_index, load_covers_index

    # Build and save (run once, or when docs change)
    index = build_covers_index(Path("docs"))
    save_covers_index(index, Path("docs/covers_index.json"))

    # Load and query (every doc-master invocation)
    index = load_covers_index(Path("docs/covers_index.json"))
    affected = get_affected_docs(["plugins/autonomous-dev/lib/foo.py"], index)
    # -> ["docs/LIBRARIES.md", "docs/ARCHITECTURE-OVERVIEW.md"]
"""

from __future__ import annotations

import fnmatch
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def build_covers_index(docs_dir: Path) -> dict[str, list[str]]:
    """Build a mapping from source paths to doc files that cover them.

    Scans all *.md files in docs_dir for YAML frontmatter containing a
    `covers:` list. Returns a dict mapping each covers entry to the list
    of doc files that declare coverage of that path.

    Args:
        docs_dir: Directory containing markdown documentation files.

    Returns:
        Dict mapping source paths (or patterns) to sorted lists of doc file
        relative paths, e.g. {"plugins/lib/": ["docs/LIBRARIES.md"]}.
    """
    index: dict[str, list[str]] = {}

    for md_file in sorted(docs_dir.glob("*.md")):
        covers = _extract_covers(md_file)
        if not covers:
            continue

        # Build relative path like "docs/FILENAME.md"
        doc_rel = f"{docs_dir.name}/{md_file.name}"

        for source_path in covers:
            if source_path not in index:
                index[source_path] = []
            if doc_rel not in index[source_path]:
                index[source_path].append(doc_rel)

    # Sort doc lists for determinism
    for key in index:
        index[key] = sorted(index[key])

    return index


def _extract_covers(md_file: Path) -> list[str]:
    """Extract the covers list from YAML frontmatter of a markdown file.

    Args:
        md_file: Path to a markdown file.

    Returns:
        List of cover entries, or empty list if no valid frontmatter/covers found.
    """
    try:
        content = md_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    if not content.startswith("---"):
        return []

    # Find the closing --- delimiter
    end_idx = content.find("---", 3)
    if end_idx == -1:
        return []

    frontmatter_text = content[3:end_idx].strip()
    if not frontmatter_text:
        return []

    try:
        frontmatter = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError:
        return []

    if not isinstance(frontmatter, dict):
        return []

    covers = frontmatter.get("covers")
    if not isinstance(covers, list):
        return []

    # Ensure all entries are strings
    return [str(entry) for entry in covers if entry is not None]


def get_affected_docs(
    changed_files: list[str],
    index: dict[str, list[str]],
) -> list[str]:
    """Find which doc files are affected by a set of changed source files.

    Matches changed files against index keys using:
    - Exact match: changed_file == index_key
    - Prefix match: index_key ends with '/' and changed_file starts with it
    - Glob match: index_key contains '*', matched with fnmatch

    Args:
        changed_files: List of changed file paths (relative).
        index: Pre-computed covers index from build_covers_index or load_covers_index.

    Returns:
        Deduplicated, sorted list of affected doc file paths.
    """
    affected: set[str] = set()

    for changed_file in changed_files:
        for index_key, doc_files in index.items():
            matched = False

            if changed_file == index_key:
                matched = True
            elif index_key.endswith("/") and changed_file.startswith(index_key):
                matched = True
            elif "*" in index_key and fnmatch.fnmatch(changed_file, index_key):
                matched = True

            if matched:
                affected.update(doc_files)

    return sorted(affected)


def save_covers_index(index: dict[str, list[str]], output_path: Path) -> None:
    """Save the covers index as formatted JSON with metadata.

    Args:
        index: The covers index mapping source paths to doc files.
        output_path: Path where the JSON file will be written.
    """
    data: dict[str, Any] = {
        "_generated": datetime.now(timezone.utc).isoformat(),
        "_doc_count": len({doc for docs in index.values() for doc in docs}),
    }
    data.update(dict(sorted(index.items())))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def load_covers_index(index_path: Path) -> dict[str, list[str]]:
    """Load a covers index from JSON, stripping metadata keys.

    Args:
        index_path: Path to the JSON index file.

    Returns:
        The covers index dict without metadata (keys starting with '_').

    Raises:
        FileNotFoundError: If index_path does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    data = json.loads(index_path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}
