"""Regression tests for _extract_metadata() using the REAL Claude Code transcript schema.

These tests document the canonical transcript JSONL format where model, usage, and content
are nested inside entry["message"] (NOT at the top level). They would fail against the
pre-fix extractor that read these fields from the top level.

Fixtures represent actual Claude Code transcript entries (schema v2.x).
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

# Import pattern follows tests/unit/hooks/test_conversation_archiver.py
REPO_ROOT = Path(__file__).resolve().parents[3]
HOOKS_DIR = REPO_ROOT / "plugins" / "autonomous-dev" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import conversation_archiver


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def real_format_transcript_path(tmp_path):
    """Write a JSONL transcript matching the real Claude Code schema.

    Layout (7 lines total):
      1. user with string content
      2. assistant: 1 text block + 1 tool_use + usage (input=1200, output=300,
         cache_read=5000, cache_creation=800)
      3. user with list content (tool_result only — no text)
      4. assistant: 2 tool_use blocks + usage (input=800, output=150,
         cache_read=6000, cache_creation=0)
      5. noise: attachment entry — MUST NOT be counted
      6. noise: permission-mode entry — MUST NOT be counted
      7. literal malformed JSON line — MUST be skipped without crashing

    Expected aggregates:
      message_count=4 (noise lines + malformed line excluded)
      user_messages=2, assistant_messages=2
      tool_calls=3 (1 in line 2 + 2 in line 4)
      total_input_tokens=2000 (1200 + 800)
      total_output_tokens=450 (300 + 150)
      total_cache_read_tokens=11000 (5000 + 6000)
      total_cache_creation_tokens=800 (800 + 0)
      model="claude-opus-4-7"
      first_user_prompt="Plan the implementation of the cache-token fix"
    """
    transcript = tmp_path / "transcript.jsonl"

    line1 = json.dumps(
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": "Plan the implementation of the cache-token fix",
            },
            "uuid": "u1",
            "timestamp": "2026-04-20T10:00:00Z",
        }
    )
    line2 = json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "model": "claude-opus-4-7",
                "content": [
                    {"type": "text", "text": "I'll start by reading the hook."},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Read",
                        "input": {"file_path": "/tmp/x"},
                    },
                ],
                "usage": {
                    "input_tokens": 1200,
                    "output_tokens": 300,
                    "cache_read_input_tokens": 5000,
                    "cache_creation_input_tokens": 800,
                },
            },
            "uuid": "a1",
        }
    )
    line3 = json.dumps(
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_1",
                        "content": "file content",
                    }
                ],
            },
            "uuid": "u2",
        }
    )
    line4 = json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "model": "claude-opus-4-7",
                "content": [
                    {"type": "tool_use", "id": "toolu_2", "name": "Edit", "input": {}},
                    {"type": "tool_use", "id": "toolu_3", "name": "Write", "input": {}},
                ],
                "usage": {
                    "input_tokens": 800,
                    "output_tokens": 150,
                    "cache_read_input_tokens": 6000,
                    "cache_creation_input_tokens": 0,
                },
            },
            "uuid": "a2",
        }
    )
    line5 = json.dumps(
        {"type": "attachment", "attachment": {"file_path": "/tmp/screenshot.png"}}
    )
    line6 = json.dumps({"type": "permission-mode", "mode": "plan"})
    line7 = "{not valid json"

    transcript.write_text(
        "\n".join([line1, line2, line3, line4, line5, line6, line7]) + "\n",
        encoding="utf-8",
    )
    return transcript


# ---------------------------------------------------------------------------
# Test: Real-schema extraction (11 tests)
# ---------------------------------------------------------------------------


class TestRealSchemaExtraction:
    """Verify _extract_metadata correctly parses the real Claude Code schema."""

    def test_message_count_excludes_noise(self, real_format_transcript_path):
        """Only user/assistant entries count — attachments, permission-mode, and
        malformed lines must not increment message_count."""
        meta = conversation_archiver._extract_metadata(
            real_format_transcript_path, hook_input={}
        )
        assert meta["message_count"] == 4

    def test_user_message_count(self, real_format_transcript_path):
        """Two user entries in the fixture."""
        meta = conversation_archiver._extract_metadata(
            real_format_transcript_path, hook_input={}
        )
        assert meta["user_messages"] == 2

    def test_assistant_message_count(self, real_format_transcript_path):
        """Two assistant entries in the fixture."""
        meta = conversation_archiver._extract_metadata(
            real_format_transcript_path, hook_input={}
        )
        assert meta["assistant_messages"] == 2

    def test_model_extracted_from_nested_message(self, real_format_transcript_path):
        """Model lives at entry['message']['model'], NOT at entry['model']."""
        meta = conversation_archiver._extract_metadata(
            real_format_transcript_path, hook_input={}
        )
        assert meta["model"] == "claude-opus-4-7"

    def test_input_tokens_summed(self, real_format_transcript_path):
        """input_tokens summed across assistant usage blocks (1200 + 800)."""
        meta = conversation_archiver._extract_metadata(
            real_format_transcript_path, hook_input={}
        )
        assert meta["total_input_tokens"] == 2000

    def test_output_tokens_summed(self, real_format_transcript_path):
        """output_tokens summed across assistant usage blocks (300 + 150)."""
        meta = conversation_archiver._extract_metadata(
            real_format_transcript_path, hook_input={}
        )
        assert meta["total_output_tokens"] == 450

    def test_cache_read_tokens_summed(self, real_format_transcript_path):
        """cache_read_input_tokens summed (5000 + 6000)."""
        meta = conversation_archiver._extract_metadata(
            real_format_transcript_path, hook_input={}
        )
        assert meta["total_cache_read_tokens"] == 11000

    def test_cache_creation_tokens_summed(self, real_format_transcript_path):
        """cache_creation_input_tokens summed (800 + 0)."""
        meta = conversation_archiver._extract_metadata(
            real_format_transcript_path, hook_input={}
        )
        assert meta["total_cache_creation_tokens"] == 800

    def test_tool_calls_from_content_blocks(self, real_format_transcript_path):
        """tool_use blocks are nested inside assistant message content — count them
        (1 in line 2, 2 in line 4 = 3 total)."""
        meta = conversation_archiver._extract_metadata(
            real_format_transcript_path, hook_input={}
        )
        assert meta["tool_calls"] == 3

    def test_first_user_prompt_from_string_content(self, real_format_transcript_path):
        """First user content is a plain string — extract verbatim."""
        meta = conversation_archiver._extract_metadata(
            real_format_transcript_path, hook_input={}
        )
        assert (
            meta["first_user_prompt"]
            == "Plan the implementation of the cache-token fix"
        )

    def test_malformed_line_does_not_crash(self, real_format_transcript_path):
        """Malformed JSONL lines must be skipped silently (defense in depth)."""
        meta = conversation_archiver._extract_metadata(
            real_format_transcript_path, hook_input={}
        )
        # If we got here without exception, the malformed line was handled.
        assert isinstance(meta, dict)


# ---------------------------------------------------------------------------
# Test: Edge cases (6 tests)
# ---------------------------------------------------------------------------


class TestRealSchemaEdgeCases:
    """Edge cases around empty input, unicode, truncation, and content shapes."""

    def test_empty_transcript(self, tmp_path):
        """Empty file produces zero counts, None model, None prompt."""
        transcript = tmp_path / "empty.jsonl"
        transcript.write_text("")

        meta = conversation_archiver._extract_metadata(transcript, hook_input={})

        assert meta["message_count"] == 0
        assert meta["user_messages"] == 0
        assert meta["assistant_messages"] == 0
        assert meta["tool_calls"] == 0
        assert meta["total_input_tokens"] == 0
        assert meta["total_output_tokens"] == 0
        assert meta["total_cache_read_tokens"] == 0
        assert meta["total_cache_creation_tokens"] == 0
        assert meta["model"] is None
        assert meta["first_user_prompt"] is None

    def test_no_assistant_entries(self, tmp_path):
        """User-only transcript: model None, all token counters 0."""
        transcript = tmp_path / "user_only.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "user",
                    "message": {"role": "user", "content": "hello"},
                }
            )
            + "\n"
        )

        meta = conversation_archiver._extract_metadata(transcript, hook_input={})

        assert meta["user_messages"] == 1
        assert meta["assistant_messages"] == 0
        assert meta["model"] is None
        assert meta["total_input_tokens"] == 0
        assert meta["total_output_tokens"] == 0
        assert meta["total_cache_read_tokens"] == 0
        assert meta["total_cache_creation_tokens"] == 0

    def test_content_as_empty_list(self, tmp_path):
        """Assistant with content=[] must not crash and yields 0 tool_calls."""
        transcript = tmp_path / "empty_content.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-opus-4-7",
                        "content": [],
                        "usage": {"input_tokens": 10, "output_tokens": 5},
                    },
                }
            )
            + "\n"
        )

        meta = conversation_archiver._extract_metadata(transcript, hook_input={})

        assert meta["assistant_messages"] == 1
        assert meta["tool_calls"] == 0
        assert meta["model"] == "claude-opus-4-7"

    def test_first_user_prompt_unicode(self, tmp_path):
        """Unicode characters in the first prompt are preserved."""
        transcript = tmp_path / "unicode.jsonl"
        prompt = "héllo 日本語 🚀"
        transcript.write_text(
            json.dumps(
                {
                    "type": "user",
                    "message": {"role": "user", "content": prompt},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        meta = conversation_archiver._extract_metadata(transcript, hook_input={})

        assert meta["first_user_prompt"] == prompt

    def test_first_user_prompt_truncation_200_chars(self, tmp_path):
        """Prompts longer than MAX_PROMPT_LENGTH are truncated to 200 chars."""
        transcript = tmp_path / "long.jsonl"
        long_prompt = "x" * 500
        transcript.write_text(
            json.dumps(
                {
                    "type": "user",
                    "message": {"role": "user", "content": long_prompt},
                }
            )
            + "\n"
        )

        meta = conversation_archiver._extract_metadata(transcript, hook_input={})

        assert meta["first_user_prompt"] is not None
        assert len(meta["first_user_prompt"]) == 200
        assert len(meta["first_user_prompt"]) == conversation_archiver.MAX_PROMPT_LENGTH

    def test_first_user_prompt_from_list_content_text_block(self, tmp_path):
        """User content as a list with a text block is extracted from the text field."""
        transcript = tmp_path / "list_content.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "hello from text block"}
                        ],
                    },
                }
            )
            + "\n"
        )

        meta = conversation_archiver._extract_metadata(transcript, hook_input={})

        assert meta["first_user_prompt"] == "hello from text block"


# ---------------------------------------------------------------------------
# Test: SQLite schema with new cache token columns (4 tests)
# ---------------------------------------------------------------------------


def _make_entry_with_cache_tokens(
    session_id: str = "test_sess",
    cache_read: int = 11000,
    cache_creation: int = 800,
) -> dict:
    """Build a complete index entry dict including cache token columns."""
    return {
        "session_id": session_id,
        "project": "test_project",
        "cwd": "/tmp/project",
        "archive_path": "/archive/test.jsonl",
        "first_seen": "2026-04-20T10:00:00+00:00",
        "last_updated": "2026-04-20T10:00:00+00:00",
        "message_count": 4,
        "user_messages": 2,
        "assistant_messages": 2,
        "tool_calls": 3,
        "total_input_tokens": 2000,
        "total_output_tokens": 450,
        "total_cache_read_tokens": cache_read,
        "total_cache_creation_tokens": cache_creation,
        "transcript_bytes": 1024,
        "model": "claude-opus-4-7",
        "first_user_prompt": "test",
    }


class TestSqliteSchemaExtended:
    """Verify the sessions table includes cache token columns and migrates legacy DBs."""

    def test_cache_columns_present_in_fresh_db(self, tmp_path):
        """Fresh DB must include both cache token columns on creation."""
        db_path = tmp_path / "sessions.db"
        entry = _make_entry_with_cache_tokens()

        conversation_archiver._update_sqlite_index(db_path, entry)

        conn = sqlite3.connect(str(db_path))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        conn.close()

        assert "total_cache_read_tokens" in cols
        assert "total_cache_creation_tokens" in cols

    def test_cache_columns_migration_on_existing_db(self, tmp_path):
        """Legacy 15-column DB must be migrated to include cache token columns."""
        db_path = tmp_path / "sessions.db"

        # Create legacy schema manually (no cache token columns)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY, project TEXT, cwd TEXT, archive_path TEXT,
                first_seen TEXT, last_updated TEXT, message_count INTEGER,
                user_messages INTEGER, assistant_messages INTEGER, tool_calls INTEGER,
                total_input_tokens INTEGER, total_output_tokens INTEGER,
                transcript_bytes INTEGER, model TEXT, first_user_prompt TEXT
            )"""
        )
        conn.commit()

        # Verify legacy schema has exactly 15 columns (no cache columns)
        legacy_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        conn.close()
        assert "total_cache_read_tokens" not in legacy_cols
        assert "total_cache_creation_tokens" not in legacy_cols

        # Call the update function — should idempotently migrate the schema
        entry = _make_entry_with_cache_tokens()
        conversation_archiver._update_sqlite_index(db_path, entry)

        conn = sqlite3.connect(str(db_path))
        new_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        conn.close()

        assert "total_cache_read_tokens" in new_cols
        assert "total_cache_creation_tokens" in new_cols

    def test_cache_values_persisted(self, tmp_path):
        """Cache token values written through _update_sqlite_index are readable via SQL."""
        db_path = tmp_path / "sessions.db"
        entry = _make_entry_with_cache_tokens(cache_read=11000, cache_creation=800)

        conversation_archiver._update_sqlite_index(db_path, entry)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT total_cache_read_tokens, total_cache_creation_tokens "
            "FROM sessions WHERE session_id = ?",
            ("test_sess",),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == 11000
        assert row[1] == 800

    def test_migration_is_idempotent(self, tmp_path):
        """Running the update function 3 times must not produce duplicate columns."""
        db_path = tmp_path / "sessions.db"
        entry = _make_entry_with_cache_tokens()

        # Call 3 times
        conversation_archiver._update_sqlite_index(db_path, entry)
        conversation_archiver._update_sqlite_index(db_path, entry)
        conversation_archiver._update_sqlite_index(db_path, entry)

        conn = sqlite3.connect(str(db_path))
        col_names = [
            row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        ]
        conn.close()

        # Each cache column must appear exactly once
        assert col_names.count("total_cache_read_tokens") == 1
        assert col_names.count("total_cache_creation_tokens") == 1
