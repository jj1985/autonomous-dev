# Setting up autonomous-dev from a fork

This doc is for maintainers who have forked `akaszubski/autonomous-dev` (for example, to `yourusername/autonomous-dev`) and want to install it on a fresh machine while keeping the fork as `origin` and the upstream as `upstream` for pulling future updates.

If you are a regular user with no fork, use the standard bootstrap from the main README — this doc is for fork maintainers.

---

## Three install approaches — pick one

### Approach A — Fork-aware curl bootstrap (one-time fork edit)

The upstream `install.sh` hardcodes `GITHUB_REPO="akaszubski/autonomous-dev"` near the top of the file (around line 56). For the curl one-liner to pull from your fork, edit `install.sh` once in the fork and commit:

```bash
# on a machine that already has your fork checked out:
sed -i '' 's|GITHUB_REPO="akaszubski/autonomous-dev"|GITHUB_REPO="yourusername/autonomous-dev"|' install.sh
git commit -am "chore: point install.sh at yourusername fork"
git push origin master
```

Then on the new machine:

```bash
bash <(curl -sSL https://raw.githubusercontent.com/yourusername/autonomous-dev/master/install.sh)
# Follow the prompts. Restart Claude Code when done, then run `/setup`.
```

**Tradeoff**: creates a single-line diff between your fork's `install.sh` and `akaszubski/master`. You'll need to preserve it across upstream merges (or re-apply after each merge). Best for forks you intend to use as a long-term install source.

### Approach B — Clone-first (recommended for fork maintainers)

Skip `install.sh` entirely — it's designed for non-developer users bootstrapping from a curl one-liner. If you maintain the fork, clone directly and deploy via the existing scripts.

```bash
# 1. Clone your fork
cd ~
git clone https://github.com/yourusername/autonomous-dev.git
cd autonomous-dev

# 2. Wire the upstream remote so you can pull akaszubski updates later
git remote add upstream https://github.com/akaszubski/autonomous-dev.git

# 3. Create a Python venv and install test dependencies
python3 -m venv .venv
.venv/bin/pip install pytest hypothesis pyyaml pytest-cov

# 4. Deploy the plugin into the global ~/.claude/ and this repo's .claude/
bash scripts/deploy-all.sh --local --skip-validate
# --local skips any SSH-based Mac Studio / remote deploy
# --skip-validate trades thoroughness for speed; omit if you want the validation pass

# 5. Sanity check
ls ~/.claude/hooks/ | head       # global hooks installed
ls .claude/                       # agents/ commands/ hooks/ lib/ skills/ etc.

# 6. Open Claude Code in this directory. Global CLAUDE.md, project CLAUDE.md,
#    and all skills/hooks/agents auto-load.
```

### Approach C — GUI clone + `/setup` wizard

If you prefer a graphical git client:

1. Use GitHub Desktop / VS Code / JetBrains to clone `https://github.com/yourusername/autonomous-dev.git`.
2. From a terminal in the cloned dir, run:
   ```bash
   git remote add upstream https://github.com/akaszubski/autonomous-dev.git
   python3 -m venv .venv
   .venv/bin/pip install pytest hypothesis pyyaml pytest-cov
   ```
3. Open the repo in Claude Code and run `/setup` — the setup wizard handles the equivalent of Approach B step 4 interactively, with prompts for customization.

---

## Ongoing workflow after install

### Push your own work to the fork

```bash
git push origin <branch>
git push origin master
```

### Pull updates from the akaszubski upstream

Weekly or when you notice upstream activity:

```bash
git fetch upstream
git log HEAD..upstream/master --oneline      # see what's new
git merge upstream/master                     # or: git rebase upstream/master
git push origin master
bash scripts/deploy-all.sh --local            # redeploy plugin into .claude/ + ~/.claude/
```

### Deploy local plugin changes

Whenever you modify anything under `plugins/autonomous-dev/*` on this repo (agents, commands, hooks, skills, lib, config, templates):

```bash
bash scripts/deploy-all.sh --local
```

This rsyncs the changes into `~/.claude/` (global) and `.claude/` (this repo's installed copy). Hooks check for this — stale installs show up in test failures and hook log warnings.

### Run tests

```bash
.venv/bin/pytest tests/unit/skills/ -q         # quick subset
.venv/bin/pytest --tb=short -q                 # full deterministic suite
.venv/bin/pytest tests/unit/skills/test_skill_descriptions.py -q  # just skill descriptions
```

---

## One-time fork housekeeping

### 1. Disable GitHub Actions on your fork (optional)

A fresh fork inherits upstream's workflows. Unless you intend to use them, disable CI runs on every push to avoid burning Actions minutes:

1. Go to `https://github.com/yourusername/autonomous-dev/settings/actions`.
2. Choose "Disable Actions" or set to manual/workflow-level permission.

### 2. Restore local hook config (if clobbered)

`.claude/settings.local.json` holds your personal hook configuration. If a deploy or fresh clone overwrites it:

- Restore from a backup (e.g., if you saved one at `/tmp/autonomous-dev-settings.local.json`).
- Or recreate it by copying the relevant hook registrations from `.claude/settings.json` into `.claude/settings.local.json`.

### 3. Git identity

If your commits show a default machine user like `user <user@macmini.local>`, set git config once:

```bash
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
```

To rewrite the most recent commit's author after setting this:

```bash
git commit --amend --reset-author --no-edit
```

### 4. Upstreaming fork changes

If your fork has commits worth contributing back:

```bash
gh pr create --repo akaszubski/autonomous-dev \
  --head yourusername:master --base master \
  --title "feat: <description>"
```

Upstream acceptance is at the maintainer's discretion; otherwise your changes live on your fork indefinitely.

---

## Troubleshooting

### Hooks don't fire after install

- Restart Claude Code (`Cmd+Q` on macOS, relaunch).
- Check that `~/.claude/hooks/*.py` exists and is executable (`ls -la ~/.claude/hooks/`).
- Look at `.claude/settings.json` and `~/.claude/settings.json` for hook registration entries.
- Re-run `bash scripts/deploy-all.sh --local --skip-validate` and check its output for errors.

### Tests fail to collect with `ModuleNotFoundError: plugins.autonomous_dev`

This is a known pre-existing issue with ~35 test modules in `tests/unit/`. The repo has a path-layout mismatch (`plugins/autonomous-dev/` isn't a Python package). It's unrelated to your fork setup — runs affecting `tests/unit/skills/`, `tests/unit/hooks/`, `tests/regression/smoke/`, `tests/property/`, etc. still pass.

### Subagent can't reach an MCP tool that works at the top level

Known limitation: subagent MCP scope is derived from project `.mcp/config.json`, not from user-level claude.ai connectors. If you need a subagent to access an MCP server you have at the user level, register it in the project's `.mcp/config.json` instead. See the commit history for `feat: Context7 MCP preference — coordinator-level scope` for one such case.

---

## See also

- Main `README.md` — non-fork install and feature overview.
- `CLAUDE.md` — critical rules (no direct edits to `agents/`, `commands/`, `hooks/`, `lib/`, `skills/*/SKILL.md` without `/implement`).
- `scripts/deploy-all.sh` — deployment script source of truth; read the header comment for all flags.
- `install.sh` — upstream curl bootstrap (if you chose Approach A, this is what you modified).
