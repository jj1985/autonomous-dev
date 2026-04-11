#!/usr/bin/env bash
# run_mutation_tests.sh — Run mutation testing with mutmut on lib/ files
#
# Usage:
#   bash scripts/run_mutation_tests.sh                  # Run against 3 critical files
#   bash scripts/run_mutation_tests.sh --file <path>    # Run against a single file
#   bash scripts/run_mutation_tests.sh --ci             # CI mode (summary output, non-blocking)
#   bash scripts/run_mutation_tests.sh --all            # Run against all of lib/
#
# Exit codes:
#   Always exits 0 (non-blocking). Future versions may exit 1 when mutation
#   score drops below threshold for --ci mode.
#
# Recovery options:
#   If mutmut cache is corrupted, run: mutmut run --no-cache
#   To clear cache manually: rm -rf .mutmut-cache/
#
# Prerequisites:
#   pip install mutmut>=2.4.0
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LIB_DIR="$REPO_ROOT/plugins/autonomous-dev/lib"

# Critical files to target by default
CRITICAL_FILES=(
    "$LIB_DIR/pipeline_state.py"
    "$LIB_DIR/tool_validator.py"
    "$LIB_DIR/settings_generator.py"
)

# Parse arguments
FILE_TARGET=""
CI_MODE=false
ALL_MODE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --file)
            FILE_TARGET="$2"
            shift 2
            ;;
        --ci)
            CI_MODE=true
            shift
            ;;
        --all)
            ALL_MODE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--file <path>] [--ci] [--all]"
            echo ""
            echo "Options:"
            echo "  --file <path>   Scope mutation testing to a single file"
            echo "  --ci            CI mode: summary output, non-blocking"
            echo "  --all           Run against all files in lib/"
            echo ""
            echo "Default: runs against pipeline_state.py, tool_validator.py, settings_generator.py"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 0
            ;;
    esac
done

# Check mutmut is installed
if ! command -v mutmut &>/dev/null; then
    echo "ERROR: mutmut is not installed."
    echo "Install with: pip install mutmut>=2.4.0"
    echo "Or: pip install -r plugins/autonomous-dev/requirements-dev.txt"
    exit 0
fi

# Check lib directory exists
if [[ ! -d "$LIB_DIR" ]]; then
    echo "ERROR: lib directory not found: $LIB_DIR"
    exit 0
fi

cd "$REPO_ROOT"

# Determine which files to mutate
if [[ -n "$FILE_TARGET" ]]; then
    echo "=== Mutation Testing: $FILE_TARGET ==="
    mutmut run --paths-to-mutate="$FILE_TARGET" || true
elif [[ "$ALL_MODE" == true ]]; then
    echo "=== Mutation Testing: All of lib/ ==="
    mutmut run || true
else
    echo "=== Mutation Testing: Critical Files ==="
    for file in "${CRITICAL_FILES[@]}"; do
        if [[ -f "$file" ]]; then
            rel_path="${file#$REPO_ROOT/}"
            echo ""
            echo "--- Mutating: $rel_path ---"
            mutmut run --paths-to-mutate="$rel_path" || true
        else
            echo "WARNING: File not found: $file"
        fi
    done
fi

echo ""
echo "=== Mutation Testing Results ==="
mutmut results || true

if [[ "$CI_MODE" == true ]]; then
    echo ""
    echo "=== CI Summary ==="
    # Show compact summary for CI pipelines
    mutmut results --ci 2>/dev/null || mutmut results 2>/dev/null || echo "No results available"
fi

echo ""
echo "Done. Exit code: 0 (non-blocking)"
exit 0
