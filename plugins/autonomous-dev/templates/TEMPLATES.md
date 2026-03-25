# Templates Directory

**Purpose**: Starter content for workspace initialization
**Version**: 1.0

---

## Overview

This directory contains templates that are automatically copied to user workspaces when the plugin is first used. This follows industry-standard patterns from git, Docker, VSCode, and other plugin ecosystems.

### Architecture

```
plugins/autonomous-dev/
├── templates/                     # Source of truth (immutable)
│   └── knowledge/                 # Knowledge base template
│       ├── INDEX.md
│       ├── README.md
│       ├── best-practices/
│       │   └── claude-code-2.0.md
│       ├── patterns/
│       └── research/
│
└── (user workspace after bootstrap)
    .claude/
    └── knowledge/                 # Bootstrapped instance (mutable)
        ├── INDEX.md              # ← From template + user updates
        ├── best-practices/       # ← From template + user research
        └── research/             # ← User research only
```

---

## How It Works

### Automatic Bootstrap

The researcher agent automatically bootstraps the knowledge base on first use:

1. **User invokes researcher**: "Research Python testing best practices"
2. **Agent checks**: Does `.claude/knowledge/` exist?
3. **If NO**: Copy from `templates/knowledge/` → `.claude/knowledge/`
4. **If YES**: Skip (already bootstrapped)
5. **Continue research**: Use bootstrapped knowledge base

### First-Time Experience

**New workspace**:
```bash
# User installs plugin
/plugin install autonomous-dev

# User requests research (first time)
"Research authentication patterns"

# Agent automatically:
✅ Initializing knowledge base from template...
✅ Copied starter knowledge (Claude Code 2.0 best practices)
✅ Knowledge base ready: .claude/knowledge/

# User gets immediate value:
- Professional knowledge base structure
- Claude Code 2.0 best practices
- Ready to add their own research
```

**Existing workspace**:
```bash
# Knowledge base already exists
"Research API design patterns"

# Agent checks:
✅ Knowledge base exists
✅ Checking INDEX for "API design"...

# Fast check, continues immediately
```

---

## Template Contents

### global-claude.md.template

**NEW in v3.40.0**: Global CLAUDE.md template for `~/.claude/CLAUDE.md`.

**Purpose**: Universal instructions that apply to ALL projects using Claude Code with autonomous-dev.

**Contents** (8KB):
- Documentation alignment validation
- Git automation best practices
- Claude Code restart requirements (critical!)
- Core philosophy for autonomous development
- Code quality standards (Python, API design)
- Testing requirements
- Problem-solving approach

**Section Markers**:
```markdown
<!-- autonomous-dev:start -->
## Documentation Alignment
...
<!-- autonomous-dev:end -->
```

Content between markers is updated when plugin updates. User content outside markers is preserved.

**Installation**:
```bash
# Via setup wizard (interactive)
python3 .claude/hooks/setup.py
# Choose: "Setup global CLAUDE.md"

# Via command line (automated)
python3 .claude/hooks/setup.py --auto --global-claude

# Standalone
python3 plugins/autonomous-dev/lib/claude_merger.py --template templates/global-claude.md.template
```

**Merge Library**: `lib/claude_merger.py` handles section-based merging with backup.

---

### knowledge/

Knowledge base template with:

- **INDEX.md**: Catalog of all knowledge entries
- **README.md**: How to use the knowledge base
- **best-practices/**: Industry standards and proven approaches
  - `claude-code-2.0.md`: Plugin development best practices
- **patterns/**: Recurring code patterns (empty, user populates)
- **research/**: Exploratory findings (empty, user populates)

### Starter Knowledge

**Claude Code 2.0 best practices** (10KB):
- Agent file format and frontmatter
- Skill creation and auto-activation
- Hook configuration and lifecycle events
- Command structure (slash commands)
- Artifact-based communication patterns
- Tool restriction security patterns
- Model optimization (opus/sonnet/haiku)
- Common mistakes to avoid

---

## Separation of Concerns

| Component | Location | Ownership | Lifecycle |
|-----------|----------|-----------|-----------|
| **Template** | `plugins/.../templates/` | Plugin developer | Updated with plugin |
| **Global CLAUDE.md** | `~/.claude/CLAUDE.md` | User (merged) | Section-based updates |
| **Workspace** | `.claude/knowledge/` | User | User adds research |
| **Cache** | `.claude/cache/` | User | Auto-expire (ephemeral) |

### What's Committed

**Plugin repository**:
```
✅ plugins/autonomous-dev/templates/knowledge/  # Source template
❌ .claude/knowledge/                           # Ignored (user data)
❌ .claude/cache/                               # Ignored (ephemeral)
```

**User workspace** (optional):
```
❌ .claude/knowledge/  # In .gitignore by default
✅ .claude/knowledge/  # User can commit if team shares knowledge
```

---

## Updates & Versioning

### Plugin Updates

When plugin is updated (v2.0 → v2.1):

**Template changes**:
- New best practices added to `templates/knowledge/`
- Updated starter knowledge

**User workspace**:
- NOT automatically updated (user data is sacred)
- User can manually merge new template entries
- Future: Agent detects and suggests new entries

### Detecting Template Updates

Future enhancement:
```python
# In researcher agent
def check_template_updates():
    """Suggest new knowledge from updated template."""
    template = read_index("plugins/.../templates/knowledge/INDEX.md")
    workspace = read_index(".claude/knowledge/INDEX.md")

    new_entries = find_missing_entries(template, workspace)

    if new_entries:
        print(f"💡 New knowledge available in plugin v{version}:")
        for entry in new_entries:
            print(f"  - {entry['title']}")
        print("\nAdd to your knowledge base? (y/n)")
```

---

## Best Practices

### For Plugin Developers

**Adding Starter Knowledge**:
1. Add new `.md` files to `templates/knowledge/best-practices/`
2. Update `templates/knowledge/INDEX.md`
3. Update version in `plugin.json`
4. Document in CHANGELOG

**DON'T**:
- Don't include workspace-specific research
- Don't include user data or secrets
- Don't make templates too large (keep <1MB total)

### For Users

**Customizing Knowledge Base**:
```bash
# Your .claude/knowledge/ is yours to modify
- Add new research
- Edit existing entries
- Reorganize as needed
- Share with team (optional)

# Template is just a starting point
# Your workspace evolves independently
```

**Resetting to Template**:
```bash
# If you want a fresh start
rm -rf .claude/knowledge/

# Next research will re-bootstrap from template
"Research something"
→ ✅ Initialized from template
```

---

## Architecture Rationale

### Why Templates + Bootstrap?

**Compared to alternatives**:

| Approach | Pros | Cons |
|----------|------|------|
| **No starter knowledge** | Simple | Poor first-time experience |
| **Knowledge in plugin code** | Always updated | User data mixed with code |
| **Templates + Bootstrap** ✅ | Best UX, clean separation | Requires bootstrap logic |

**Industry precedent**:
- **Git**: Template in `/usr/share/git-core/templates/`
- **Docker**: Image (template) → Container (instance)
- **npm**: `node_modules` bootstrapped from `package.json`
- **VSCode**: Extension provides snippets template

### Benefits

1. **Clean Separation**: Code vs data, template vs instance
2. **Best UX**: Users get immediate value on first use
3. **Maintainable**: Templates update with plugin, workspace is independent
4. **Scalable**: Can ship 100+ best practices, users pay for what they use
5. **Standard Pattern**: Follows established plugin ecosystem conventions

---

## Implementation Details

### Bootstrap Function

Located in `lib/search_utils.py`:

```python
def bootstrap_knowledge_base(
    workspace_kb: Optional[Path] = None,
    template_kb: Optional[Path] = None
) -> Tuple[bool, str]:
    """Bootstrap knowledge base from plugin template."""

    # Check if already exists
    if workspace_kb.exists():
        return True, "Knowledge base already exists"

    # Copy template to workspace
    if template_kb.exists():
        shutil.copytree(template_kb, workspace_kb)
        return True, "Initialized from template"

    # Fallback: Create minimal structure
    create_minimal_structure(workspace_kb)
    return True, "Created minimal structure"
```

### Auto-Invocation

Researcher agent calls on every invocation:

```python
# At start of research workflow
from plugins.autonomous_dev.lib.search_utils import bootstrap_knowledge_base

success, message = bootstrap_knowledge_base()
print(f"✅ {message}")

# Then continue with research...
```

**Performance**: <1 second if already exists (fast path check)

---

## Examples

### First Research Session

```bash
# New workspace, never used researcher before
User: "Research Docker best practices"

Agent:
✅ Initializing knowledge base from template...
✅ Copied starter knowledge from plugin
✅ Knowledge base ready: .claude/knowledge/
✅ Checking INDEX for "Docker"... not found
🔍 Starting research...
```

### Subsequent Sessions

```bash
# Workspace has knowledge base
User: "Research Kubernetes deployment"

Agent:
✅ Knowledge base exists
✅ Checking INDEX for "Kubernetes"... not found
🔍 Starting research...
```

### After Plugin Update

```bash
# Plugin updated v2.0 → v2.1
# New template has "GitHub Actions" best practices

User: "Research GitHub Actions"

Agent:
✅ Knowledge base exists
💡 New template entry available: github-actions.md
💡 Would you like to add to your knowledge base?
```

---

## Future Enhancements

**Planned**:
1. Template update detection and merge
2. Multi-language templates (Python, JS, Rust)
3. Project-type templates (web, ML, CLI)
4. Team template sharing via git submodules

---

## Support

**Questions**:
- Template not copying? Check `plugins/autonomous-dev/templates/knowledge/` exists
- Want to reset? Delete `.claude/knowledge/` and re-run researcher
- Need different starter knowledge? Edit `templates/knowledge/` in plugin

**Contribute**:
- Submit PRs with new best practices to `templates/knowledge/`
- Share your research findings (they might become templates!)

---

**Last Updated**: 2025-12-09
**Version**: 1.1
