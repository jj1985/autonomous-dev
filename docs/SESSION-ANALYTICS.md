---
covers:
  - plugins/autonomous-dev/hooks/conversation_archiver.py
  - ~/.claude/archive/
---

# Session Analytics

Every Claude Code session is archived for long-term analysis. Two layers: a SQLite summary index for fast queries and full raw transcripts on disk.

**Hook**: [conversation_archiver.py](../plugins/autonomous-dev/hooks/conversation_archiver.py) (fires on `Stop` event, per-turn)

## Locations

| What | Path |
|------|------|
| SQLite summary index | `~/.claude/archive/sessions.db` |
| Full raw transcripts | `~/.claude/archive/conversations/{YYYY-MM}/{session_id}.jsonl` |
| JSONL session index (grep/jq friendly) | `~/.claude/archive/index.jsonl` |
| Live transcript (Claude Code's own, near-real-time) | `~/.claude/projects/{project}/{session_id}.jsonl` |

The archive is populated per-turn (after each assistant response). The live file is updated entry-by-entry as Claude Code produces output.

## sessions.db Schema (17 columns)

| Column | Type | Source |
|--------|------|--------|
| `session_id` | TEXT PK | Claude Code session UUID |
| `project` | TEXT | basename of `cwd` (e.g. `realign`, `autonomous-dev`) |
| `cwd` | TEXT | Full working directory at session start |
| `archive_path` | TEXT | Path to the archived JSONL transcript |
| `first_seen` | TEXT | ISO timestamp, preserved across upserts |
| `last_updated` | TEXT | ISO timestamp, updated every Stop |
| `message_count` | INTEGER | Total conversation messages (user + assistant only) |
| `user_messages` | INTEGER | User turns |
| `assistant_messages` | INTEGER | Assistant turns |
| `tool_calls` | INTEGER | Count of `tool_use` content blocks in assistant messages |
| `total_input_tokens` | INTEGER | Fresh (non-cached) input tokens |
| `total_output_tokens` | INTEGER | Generated output tokens |
| `cache_read_tokens` | INTEGER | Tokens served from cache (0.1x base cost) |
| `cache_creation_tokens` | INTEGER | Tokens written to cache (1.25x-2.0x depending on TTL) |
| `transcript_bytes` | INTEGER | Size of the archived transcript file |
| `model` | TEXT | e.g. `claude-opus-4-7`, `claude-sonnet-4-6` |
| `first_user_prompt` | TEXT | First user message, truncated to 200 chars |

## Common Queries

**Per-repo totals**
```bash
sqlite3 -header -column ~/.claude/archive/sessions.db "
  SELECT project, COUNT(*) sessions, SUM(total_output_tokens) out_tok, SUM(tool_calls) tools
  FROM sessions GROUP BY project ORDER BY out_tok DESC;
"
```

**Recent sessions for a specific repo**
```bash
sqlite3 -header -column ~/.claude/archive/sessions.db "
  SELECT substr(session_id,1,8) sid, last_updated, message_count, model,
         substr(first_user_prompt,1,60) prompt
  FROM sessions WHERE project='autonomous-dev'
  ORDER BY last_updated DESC LIMIT 10;
"
```

**Biggest sessions by output tokens**
```bash
sqlite3 -header -column ~/.claude/archive/sessions.db "
  SELECT project, substr(session_id,1,8) sid, total_output_tokens, tool_calls,
         substr(first_user_prompt,1,50) prompt
  FROM sessions ORDER BY total_output_tokens DESC LIMIT 10;
"
```

**Cache hit rate per repo** (higher `cache_pct` = better caching, cheaper)
```bash
sqlite3 -header -column ~/.claude/archive/sessions.db "
  SELECT project,
         SUM(total_input_tokens) fresh_in,
         SUM(cache_read_tokens)  cache_read,
         ROUND(100.0 * SUM(cache_read_tokens) /
               NULLIF(SUM(cache_read_tokens + total_input_tokens), 0), 1) cache_pct
  FROM sessions GROUP BY project ORDER BY cache_read DESC;
"
```

**Find transcript file for a session**
```bash
sqlite3 ~/.claude/archive/sessions.db \
  "SELECT archive_path FROM sessions WHERE session_id LIKE 'abc12345%';"
```

**Search all history for a past prompt or output**
```bash
grep -l "search term" ~/.claude/archive/conversations/**/*.jsonl
```

## Timing

The `Stop` hook fires **after each complete assistant response**, not mid-turn. So the archive lags the live transcript by one turn. Example:

```
live file:  ~/.claude/projects/.../{session_id}.jsonl   (real-time, every entry)
archive:    ~/.claude/archive/conversations/.../         (per-turn, post-Stop)
```

If Claude Code crashes mid-turn, the live file survives (Claude Code writes it itself), but the archive may skip that partial turn. To force a flush, let Claude finish the response normally.

## Configuration

Controlled by env var `CONVERSATION_ARCHIVE` (default `true`):
- `CONVERSATION_ARCHIVE=true` — archive every Stop event
- `CONVERSATION_ARCHIVE=false` — disable archiving

Set in `~/.claude/settings.json`:
```json
{
  "hooks": {
    "Stop": [{
      "command": "CONVERSATION_ARCHIVE=true python3 ~/.claude/hooks/conversation_archiver.py",
      "timeout": 10,
      "type": "command"
    }]
  }
}
```

The hook is non-blocking (always exits 0), uses Python stdlib only, and times out at 10s.

## Per-Repo Quirk: Worktrees and Subdirectories

The `project` column is derived from the `cwd` basename at session start. This means:

- Sessions started in a worktree path like `~/Dev/autonomous-dev/.worktrees/batch-20260413-152323/` get `project = "batch-20260413-152323"` rather than folding into `autonomous-dev`.
- Sessions started in a subdirectory like `~/Dev/spektiv/frontend/` get `project = "frontend"` rather than `spektiv`.

This is by design — it lets you analyze batch-mode sessions separately from main-branch work. If you want unified analytics, group by `cwd` prefix in your query.

## Related

- [HOOKS.md](HOOKS.md) — full hook catalog
- [HOOK-REGISTRY.md](HOOK-REGISTRY.md) — hook sidecar schema
- [EVALUATION.md](EVALUATION.md) — how sessions feed the effectiveness measurement loop
- [ARCHITECTURE-OVERVIEW.md](ARCHITECTURE-OVERVIEW.md) — where session logging fits in the three-layer system

## Backfill

If you need to populate metadata from existing transcripts (e.g. after a hook bugfix), the extraction logic lives in `_extract_metadata()` in `conversation_archiver.py`. Re-parse transcripts on disk and `UPDATE sessions SET ...` — the schema supports idempotent re-writes via `INSERT OR REPLACE`.

Issue #773 introduced the SQLite index. Later fix added `cache_read_tokens` and `cache_creation_tokens` columns via idempotent `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` migration. Existing DBs auto-upgrade on the next Stop event.
