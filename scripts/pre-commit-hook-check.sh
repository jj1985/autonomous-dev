#!/bin/bash
# Pre-commit hook: Validate hook sidecar consistency
# Install: ln -sf ../../scripts/pre-commit-hook-check.sh .git/hooks/pre-commit

# Check if any hook-related files are staged
STAGED_FILES=$(git diff --cached --name-only)
if echo "$STAGED_FILES" | grep -qE '(plugins/autonomous-dev/hooks/|plugins/autonomous-dev/config/(install_manifest|global_settings_template))'; then
    echo "Hook-related files staged — checking sidecar consistency..."
    python3 scripts/generate_hook_config.py --check \
        --hooks-dir plugins/autonomous-dev/hooks \
        --manifest-path plugins/autonomous-dev/config/install_manifest.json \
        --settings-path plugins/autonomous-dev/config/global_settings_template.json \
        --schema-path plugins/autonomous-dev/config/hook-metadata.schema.json
    if [ $? -ne 0 ]; then
        echo ""
        echo "ERROR: Hook sidecar consistency check failed!"
        echo "Fix: python3 scripts/generate_hook_config.py --write"
        echo ""
        exit 1
    fi
fi
exit 0
