#!/usr/bin/env bash
# Sync this fork's master with the `upstream` remote (akaszubski/autonomous-dev).
#
# Verifies a clean working tree on master, fetches upstream, shows the
# incoming commit log + any ahead-of-upstream commits, asks for confirmation,
# merges, pushes to `origin`, and redeploys the plugin into ~/.claude/ and
# this repo's .claude/ via scripts/deploy-all.sh --local.
#
# Usage:
#   scripts/sync-upstream.sh              # interactive — asks before merging
#   scripts/sync-upstream.sh --yes        # non-interactive (skip the prompt)
#   scripts/sync-upstream.sh --dry-run    # show incoming log, no changes
#   scripts/sync-upstream.sh --no-deploy  # skip the deploy-all.sh step
#   scripts/sync-upstream.sh --help       # show this header
#
# Exit codes:
#   0  — success, or no incoming commits, or user cancelled
#   1  — preflight failure (missing upstream, dirty tree, wrong branch)
#   2  — merge produced conflicts that require manual resolution

set -euo pipefail

YES=false
DRY_RUN=false
NO_DEPLOY=false

for arg in "$@"; do
    case "$arg" in
        --yes|-y) YES=true ;;
        --dry-run) DRY_RUN=true ;;
        --no-deploy) NO_DEPLOY=true ;;
        --help|-h)
            head -16 "$0" | tail -15
            exit 0
            ;;
        *) echo "Unknown flag: $arg" >&2; exit 1 ;;
    esac
done

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info()  { printf "${GREEN}==>${NC} %s\n" "$1"; }
log_warn()  { printf "${YELLOW}WARN${NC} %s\n" "$1"; }
log_error() { printf "${RED}ERROR${NC} %s\n" "$1" >&2; }

# 1. Must be inside a git repo
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    log_error "Not a git repository"
    exit 1
}
cd "$REPO_ROOT"

# 2. Must have an `upstream` remote
if ! git remote | grep -q '^upstream$'; then
    log_error "No 'upstream' remote configured"
    echo "  Add it with:"
    echo "    git remote add upstream https://github.com/akaszubski/autonomous-dev.git"
    exit 1
fi

# 3. Working tree must be clean
if [ -n "$(git status --porcelain)" ]; then
    log_error "Working tree is not clean — commit or stash first"
    git status --short
    exit 1
fi

# 4. Must be on master
CURRENT_BRANCH="$(git branch --show-current)"
if [ "$CURRENT_BRANCH" != "master" ]; then
    log_error "Not on master (currently on: $CURRENT_BRANCH)"
    echo "  Switch with: git checkout master"
    exit 1
fi

# 5. Fetch upstream
log_info "Fetching upstream..."
git fetch upstream

# 6. Count incoming commits
INCOMING_COUNT="$(git rev-list --count HEAD..upstream/master 2>/dev/null || echo 0)"
if [ "$INCOMING_COUNT" -eq 0 ]; then
    log_info "Already up to date with upstream/master — nothing to do."
    exit 0
fi

log_info "Incoming commits from upstream/master ($INCOMING_COUNT):"
git log HEAD..upstream/master --oneline --max-count=50
echo ""

# 7. Show ahead-of-upstream commits (your fork-only work)
AHEAD_COUNT="$(git rev-list --count upstream/master..HEAD 2>/dev/null || echo 0)"
if [ "$AHEAD_COUNT" -gt 0 ]; then
    log_info "Your fork is ahead of upstream by $AHEAD_COUNT commit(s):"
    git log upstream/master..HEAD --oneline --max-count=20
    echo ""
fi

# 8. Dry run exit
if $DRY_RUN; then
    log_info "Dry run — no changes made."
    exit 0
fi

# 9. Confirm
if ! $YES; then
    read -r -p "Merge upstream/master into master? [y/N] " CONFIRM
    case "$CONFIRM" in
        y|Y|yes|YES) ;;
        *) log_info "Cancelled."; exit 0 ;;
    esac
fi

# 10. Merge
log_info "Merging upstream/master..."
if ! git merge upstream/master --no-edit; then
    log_error "Merge produced conflicts — resolve manually."
    echo ""
    echo "  After resolving:"
    echo "    git add <resolved files>"
    echo "    git commit"
    echo "    git push origin master"
    echo "    bash scripts/deploy-all.sh --local"
    exit 2
fi

# 11. Push to fork
log_info "Pushing to origin/master..."
git push origin master

# 12. Redeploy plugin
if $NO_DEPLOY; then
    log_warn "Skipped deploy step (--no-deploy). Run 'bash scripts/deploy-all.sh --local' when ready."
else
    log_info "Redeploying plugin into ~/.claude/ and .claude/..."
    bash "$REPO_ROOT/scripts/deploy-all.sh" --local --skip-validate
fi

log_info "Sync complete."
