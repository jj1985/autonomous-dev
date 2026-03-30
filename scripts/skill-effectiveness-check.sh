#!/usr/bin/env bash
#
# Run skill effectiveness harness — measures whether skills actually change behavior.
#
# Usage:
#   ./scripts/skill-effectiveness-check.sh                  # Full report (all 5 skills)
#   ./scripts/skill-effectiveness-check.sh --quick          # Degradation check only (2 prompts/skill)
#   ./scripts/skill-effectiveness-check.sh --skill python-standards  # Single skill
#   ./scripts/skill-effectiveness-check.sh --update         # Full run + update baselines
#
# Requires: OPENROUTER_API_KEY env var, openai pip package
#
# Cost estimate:
#   Full run:  ~$0.50-1.00 (5 skills × 5 prompts × 5 criteria × 2 variants)
#   Quick run: ~$0.15-0.30 (5 skills × 2 prompts)
#   Single:    ~$0.05-0.10

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- Parse args ---
MODE="full"
SKILL=""
UPDATE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --quick)
            MODE="quick"
            shift
            ;;
        --skill)
            SKILL="$2"
            shift 2
            ;;
        --update)
            UPDATE="--update-baselines"
            shift
            ;;
        --help|-h)
            head -14 "$0" | tail -13
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# --- Preflight ---
if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
    echo "ERROR: OPENROUTER_API_KEY not set"
    echo "  export OPENROUTER_API_KEY=your-key-here"
    exit 1
fi

python -c "import openai" 2>/dev/null || {
    echo "ERROR: openai package not installed"
    echo "  pip install openai"
    exit 1
}

# --- Build pytest command ---
TEST_FILE="tests/genai/skills/test_skill_effectiveness.py"
PYTEST_ARGS=(--genai --tb=short -q)

if [[ -n "$UPDATE" ]]; then
    PYTEST_ARGS+=("$UPDATE")
fi

case "$MODE" in
    quick)
        echo "=== Skill Effectiveness: Quick Degradation Check ==="
        PYTEST_ARGS+=(-k "test_no_skill_degrades")
        ;;
    full)
        if [[ -n "$SKILL" ]]; then
            echo "=== Skill Effectiveness: $SKILL ==="
            PYTEST_ARGS+=(-k "$SKILL")
        else
            echo "=== Skill Effectiveness: Full Report ==="
        fi
        ;;
esac

echo "Running from: $REPO_DIR"
echo ""

cd "$REPO_DIR"
python -m pytest "$TEST_FILE" "${PYTEST_ARGS[@]}"
EXIT_CODE=$?

echo ""

# --- Show baselines if they exist ---
BASELINES="tests/genai/skills/baselines/effectiveness.json"
if [[ -f "$BASELINES" ]] && python -c "
import json, sys
data = json.load(open('$BASELINES'))
skills = {k: v for k, v in data.items() if not k.startswith('_')}
if not skills:
    sys.exit(1)
print('Current baselines:')
for name, info in sorted(skills.items()):
    delta = info.get('delta', 0)
    rate = info.get('pass_rate_with', 0)
    status = 'OK' if delta >= 0.10 or rate >= 0.80 else 'WEAK'
    print(f'  {name:30s}  delta: {delta:+5.0%}  with: {rate:5.0%}  {status}')
" 2>/dev/null; then
    true  # baselines printed
fi

exit $EXIT_CODE
