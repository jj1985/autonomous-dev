#!/usr/bin/env python3
"""Build the covers index for doc-master optimization.

Scans docs/*.md for `covers:` YAML frontmatter and produces a JSON index
mapping source paths to the doc files that cover them.

Usage:
    python3 scripts/build_covers_index.py
    python3 scripts/build_covers_index.py --output docs/covers_index.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add lib to path for covers_index import
REPO_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

from covers_index import build_covers_index, save_covers_index


def main() -> None:
    """Build and save the covers index."""
    parser = argparse.ArgumentParser(
        description="Build the covers index for doc-master optimization."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/covers_index.json"),
        help="Output path for the JSON index (default: docs/covers_index.json)",
    )
    args = parser.parse_args()

    docs_dir = REPO_ROOT / "docs"
    if not docs_dir.is_dir():
        print(f"Error: docs directory not found at {docs_dir}", file=sys.stderr)
        sys.exit(1)

    index = build_covers_index(docs_dir)
    output_path = REPO_ROOT / args.output
    save_covers_index(index, output_path)

    # Summary
    source_paths = len(index)
    doc_files = len({doc for docs in index.values() for doc in docs})
    print(f"Covers index built: {source_paths} source paths, {doc_files} doc mappings")
    print(f"Written to: {output_path}")


if __name__ == "__main__":
    main()
