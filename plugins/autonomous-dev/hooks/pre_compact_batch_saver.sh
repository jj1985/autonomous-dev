#!/bin/bash
# pre_compact_batch_saver.sh
# PreCompact hook: saves batch state before context compaction
# Creates .claude/compaction_recovery.json marker for post-compaction recovery
# Always exits 0 (never blocks compaction)

BATCH_STATE=".claude/batch_state.json"
RECOVERY_MARKER=".claude/compaction_recovery.json"
CHECKPOINT_DIR="${CHECKPOINT_DIR:-.ralph-checkpoints}"

# If no batch state, nothing to save
if [ ! -f "$BATCH_STATE" ]; then
  exit 0
fi

# Read batch status
status=$(jq -r '.status // "unknown"' "$BATCH_STATE" 2>/dev/null || echo "unknown")
if [ "$status" != "in_progress" ]; then
  exit 0
fi

# Read batch state fields
batch_id=$(jq -r '.batch_id // ""' "$BATCH_STATE" 2>/dev/null || echo "")
current_index=$(jq -r '.current_index // 0' "$BATCH_STATE" 2>/dev/null || echo "0")
total_features=$(jq -r '.total_features // 0' "$BATCH_STATE" 2>/dev/null || echo "0")
features=$(jq -c '.features // []' "$BATCH_STATE" 2>/dev/null || echo "[]")

# Try to read RALPH checkpoint if available
checkpoint_data="{}"
if [ -n "$batch_id" ]; then
  checkpoint_file="$CHECKPOINT_DIR/ralph-${batch_id}_checkpoint.json"
  if [ -f "$checkpoint_file" ]; then
    checkpoint_data=$(cat "$checkpoint_file" 2>/dev/null || echo "{}")
  fi
fi

# Build recovery marker
timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

jq -n \
  --arg batch_id "$batch_id" \
  --arg status "$status" \
  --argjson current_index "$current_index" \
  --argjson total_features "$total_features" \
  --argjson features "$features" \
  --argjson checkpoint "$checkpoint_data" \
  --arg saved_at "$timestamp" \
  --arg compact_summary "" \
  '{
    batch_id: $batch_id,
    status: $status,
    current_index: $current_index,
    total_features: $total_features,
    features: $features,
    checkpoint: $checkpoint,
    saved_at: $saved_at,
    compact_summary: $compact_summary
  }' > "$RECOVERY_MARKER" 2>/dev/null

exit 0
