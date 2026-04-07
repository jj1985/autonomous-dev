"""Tests for covers_index library (Issue #713)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add lib to path
REPO_ROOT = Path(__file__).resolve().parents[3]
LIB_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

from covers_index import (
    build_covers_index,
    get_affected_docs,
    load_covers_index,
    save_covers_index,
)


class TestBuildCoversIndex:
    """Tests for build_covers_index function."""

    def test_build_index_from_docs(self, tmp_path: Path) -> None:
        """Creates temp docs with covers frontmatter, verifies index."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        (docs_dir / "foo.md").write_text(
            "---\ncovers:\n  - src/lib/\n---\n# Foo\nContent here.\n"
        )
        (docs_dir / "bar.md").write_text(
            "---\ncovers:\n  - src/lib/specific.py\n---\n# Bar\nContent here.\n"
        )

        index = build_covers_index(docs_dir)

        assert "src/lib/" in index
        assert "docs/foo.md" in index["src/lib/"]
        assert "src/lib/specific.py" in index
        assert "docs/bar.md" in index["src/lib/specific.py"]

    def test_multiple_covers_entries(self, tmp_path: Path) -> None:
        """Doc with multiple covers entries creates multiple index keys."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        (docs_dir / "multi.md").write_text(
            "---\ncovers:\n  - src/a/\n  - src/b/\n---\n# Multi\n"
        )

        index = build_covers_index(docs_dir)

        assert "src/a/" in index
        assert "src/b/" in index
        assert index["src/a/"] == ["docs/multi.md"]
        assert index["src/b/"] == ["docs/multi.md"]

    def test_no_frontmatter_skipped(self, tmp_path: Path) -> None:
        """Doc without frontmatter is silently skipped."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        (docs_dir / "plain.md").write_text("# Just a doc\nNo frontmatter here.\n")

        index = build_covers_index(docs_dir)
        assert index == {}

    def test_malformed_yaml_skipped(self, tmp_path: Path) -> None:
        """Doc with broken YAML is skipped without error."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        (docs_dir / "broken.md").write_text(
            "---\ncovers: [this is: broken: yaml:\n---\n# Broken\n"
        )

        index = build_covers_index(docs_dir)
        assert index == {}

    def test_no_covers_key_skipped(self, tmp_path: Path) -> None:
        """Doc with frontmatter but no covers key is skipped."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        (docs_dir / "nocov.md").write_text(
            "---\ntitle: No covers\n---\n# No covers\n"
        )

        index = build_covers_index(docs_dir)
        assert index == {}

    def test_doc_lists_sorted(self, tmp_path: Path) -> None:
        """Doc lists for each source path are sorted."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Two docs covering the same path
        (docs_dir / "z_doc.md").write_text(
            "---\ncovers:\n  - shared/path/\n---\n# Z\n"
        )
        (docs_dir / "a_doc.md").write_text(
            "---\ncovers:\n  - shared/path/\n---\n# A\n"
        )

        index = build_covers_index(docs_dir)
        assert index["shared/path/"] == ["docs/a_doc.md", "docs/z_doc.md"]

    def test_real_docs_directory(self) -> None:
        """Build index from actual docs directory (sanity check)."""
        docs_dir = REPO_ROOT / "docs"
        if not docs_dir.is_dir():
            pytest.skip("No docs directory in repo")

        index = build_covers_index(docs_dir)
        # Should find at least some entries
        assert len(index) > 0


class TestGetAffectedDocs:
    """Tests for get_affected_docs function."""

    def test_exact_match(self) -> None:
        index = {"src/foo.py": ["docs/A.md"]}
        assert get_affected_docs(["src/foo.py"], index) == ["docs/A.md"]

    def test_prefix_match(self) -> None:
        index = {"src/lib/": ["docs/A.md"]}
        assert get_affected_docs(["src/lib/bar.py"], index) == ["docs/A.md"]

    def test_prefix_no_false_positive(self) -> None:
        """Prefix match requires trailing slash to prevent partial dir matches."""
        index = {"src/lib/": ["docs/A.md"]}
        # "src/library/foo.py" should NOT match "src/lib/" prefix
        assert get_affected_docs(["src/library/foo.py"], index) == []

    def test_no_match(self) -> None:
        index = {"src/lib/": ["docs/A.md"]}
        assert get_affected_docs(["other/file.py"], index) == []

    def test_multiple_docs(self) -> None:
        index = {"src/lib/": ["docs/A.md", "docs/B.md"]}
        result = get_affected_docs(["src/lib/foo.py"], index)
        assert result == ["docs/A.md", "docs/B.md"]

    def test_glob_pattern(self) -> None:
        index = {"src/*.hook.json": ["docs/HOOKS.md"]}
        assert get_affected_docs(["src/pre_tool.hook.json"], index) == ["docs/HOOKS.md"]

    def test_glob_no_match(self) -> None:
        index = {"src/*.hook.json": ["docs/HOOKS.md"]}
        assert get_affected_docs(["src/something.py"], index) == []

    def test_deduplication(self) -> None:
        """Same doc from multiple covers entries is returned once."""
        index = {"src/a.py": ["docs/A.md"], "src/b.py": ["docs/A.md"]}
        result = get_affected_docs(["src/a.py", "src/b.py"], index)
        assert result == ["docs/A.md"]

    def test_multiple_changed_files(self) -> None:
        """Multiple changed files aggregate their affected docs."""
        index = {
            "src/a.py": ["docs/A.md"],
            "src/b.py": ["docs/B.md"],
        }
        result = get_affected_docs(["src/a.py", "src/b.py"], index)
        assert result == ["docs/A.md", "docs/B.md"]

    def test_empty_changed_files(self) -> None:
        index = {"src/lib/": ["docs/A.md"]}
        assert get_affected_docs([], index) == []

    def test_empty_index(self) -> None:
        assert get_affected_docs(["src/foo.py"], {}) == []


class TestSaveLoadRoundtrip:
    """Tests for save_covers_index and load_covers_index."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        index = {"src/lib/": ["docs/A.md", "docs/B.md"]}
        path = tmp_path / "index.json"
        save_covers_index(index, path)
        loaded = load_covers_index(path)
        assert loaded == index

    def test_metadata_stripped_on_load(self, tmp_path: Path) -> None:
        """Metadata keys (starting with _) are stripped when loading."""
        index = {"src/foo.py": ["docs/A.md"]}
        path = tmp_path / "index.json"
        save_covers_index(index, path)

        # Verify metadata exists in raw JSON
        raw = json.loads(path.read_text())
        assert "_generated" in raw
        assert "_doc_count" in raw

        # Verify metadata stripped on load
        loaded = load_covers_index(path)
        assert "_generated" not in loaded
        assert "_doc_count" not in loaded

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Save creates parent directories if they don't exist."""
        path = tmp_path / "nested" / "dir" / "index.json"
        save_covers_index({"a": ["b"]}, path)
        assert path.exists()

    def test_save_sorted_keys(self, tmp_path: Path) -> None:
        """Saved JSON has sorted keys for determinism."""
        index = {"z/path": ["docs/Z.md"], "a/path": ["docs/A.md"]}
        path = tmp_path / "index.json"
        save_covers_index(index, path)

        raw = json.loads(path.read_text())
        keys = [k for k in raw.keys() if not k.startswith("_")]
        assert keys == sorted(keys)

    def test_doc_count_metadata(self, tmp_path: Path) -> None:
        """_doc_count reflects unique doc count."""
        index = {
            "src/a.py": ["docs/A.md", "docs/B.md"],
            "src/b.py": ["docs/A.md"],  # A.md shared, should count once
        }
        path = tmp_path / "index.json"
        save_covers_index(index, path)

        raw = json.loads(path.read_text())
        assert raw["_doc_count"] == 2  # A.md and B.md

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        """Loading a nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_covers_index(tmp_path / "missing.json")
