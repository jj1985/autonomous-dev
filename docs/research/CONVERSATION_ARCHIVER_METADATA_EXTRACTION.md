---
topic: conversation_archiver metadata extraction
created: 2026-04-20
updated: 2026-04-20
sources:
  - plugins/autonomous-dev/hooks/conversation_archiver.py
  - tests/unit/hooks/test_conversation_archiver.py
  - https://platform.claude.com/docs/en/build-with-claude/prompt-caching
  - https://code.claude.com/docs/en/hooks
  - https://github.com/phuryn/claude-usage
  - https://liambx.com/blog/claude-code-log-analysis-with-duckdb
  - https://www.sqlite.org/lang_altertable.html
---

# conversation_archiver metadata extraction

## Local Research (Codebase)

1. Existing hook at plugins/autonomous-dev/hooks/conversation_archiver.py
2. _extract_metadata lines 69-152
3. _update_database/sqlite function defines schema at lines 284-301
4. Tests at tests/unit/hooks/test_conversation_archiver.py use broken fixtures
5. session_activity_logger.py has similar hook patterns

## Web Research (External Sources)

1. Schema stable across Claude Code 2.x; no legacy fallback needed
2. Cache tokens essential for cost analytics (0.1x cache_read, 1.25x cache_creation)
3. Community tools (claude-usage, claude-code-log) all use message.* path
4. Security: path traversal on transcript_path — validate within ~/.claude
5. Idempotent migration: PRAGMA table_info then ALTER TABLE ADD COLUMN with DEFAULT

## Sources

- [plugins](plugins/autonomous-dev/hooks/conversation_archiver.py)
- [tests](tests/unit/hooks/test_conversation_archiver.py)
- [platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [code.claude.com](https://code.claude.com/docs/en/hooks)
- [github.com](https://github.com/phuryn/claude-usage)
- [liambx.com](https://liambx.com/blog/claude-code-log-analysis-with-duckdb)
- [www.sqlite.org](https://www.sqlite.org/lang_altertable.html)
