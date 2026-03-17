#!/bin/bash
# post_compact_enricher.sh
# PostCompact hook: enriches recovery marker with compaction summary
# Reads compact_summary from stdin JSON and updates .claude/compaction_recovery.json
# Always exits 0 (never blocks)

RECOVERY_MARKER=".claude/compaction_recovery.json"

# Read stdin JSON
input=$(cat 2>/dev/null || echo "{}")

# If no recovery marker, nothing to enrich
if [ ! -f "$RECOVERY_MARKER" ]; then
  exit 0
fi

# Extract compact_summary from stdin
compact_summary=$(echo "$input" | jq -r '.compact_summary // ""' 2>/dev/null || echo "")

# If we got a summary, update the marker
if [ -n "$compact_summary" ]; then
  tmp_file="${RECOVERY_MARKER}.tmp"
  jq --arg summary "$compact_summary" '.compact_summary = $summary' "$RECOVERY_MARKER" > "$tmp_file" 2>/dev/null
  if [ $? -eq 0 ] && [ -s "$tmp_file" ]; then
    mv "$tmp_file" "$RECOVERY_MARKER"
  else
    rm -f "$tmp_file" 2>/dev/null
  fi
fi

exit 0
