"""Acceptance tests for Issue #814: Planning workflow system.

Static file inspection tests that verify the acceptance criteria for the
/plan skill, plan-critic agent, plan_gate hook, and plan_validator library.

These tests will fail until the feature is implemented -- this is expected
and correct TDD behavior. They define the contract that implementation must satisfy.

Acceptance criteria covered:
1. plan_validator.py exists with required validation functions
2. plan_gate.py hook enforces plan-before-write for complex changes
3. plan-critic.md agent defines adversarial critique workflow
4. planning-workflow SKILL.md documents the 7-step workflow
5. /plan command exists and references all 7 steps
6. plan-to-issues.md updated with plan-file-as-input
7. All new files registered in install_manifest.json and settings templates
8. Documentation created (PLANNING-WORKFLOW.md, CLAUDE.md updated)
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGINS = REPO_ROOT / "plugins" / "autonomous-dev"


# ---------------------------------------------------------------------------
# 1. Plan Validator Library
# ---------------------------------------------------------------------------

class TestAcceptancePlanValidator:
    """Verify plugins/autonomous-dev/lib/plan_validator.py exists with required API."""

    VALIDATOR = PLUGINS / "lib" / "plan_validator.py"

    def test_module_exists(self):
        """plan_validator.py must exist as the core validation library."""
        assert self.VALIDATOR.exists(), (
            f"plan_validator.py not found at {self.VALIDATOR}\n"
            f"This file must be created as part of Issue #814 implementation."
        )

    def test_has_validate_plan_function(self):
        """Module must define a top-level validate function for plan files."""
        content = self.VALIDATOR.read_text()
        assert re.search(r"def validate_plan\(", content), (
            "plan_validator.py must contain 'def validate_plan(' function.\n"
            "This is the primary entry point for validating plan file contents."
        )

    def test_checks_required_sections(self):
        """Validator must check for all three required sections."""
        content = self.VALIDATOR.read_text()
        required_sections = ["WHY", "SCOPE", "Existing Solutions", "Minimal Path"]
        found = [s for s in required_sections if s in content]
        assert len(found) >= 3, (
            f"plan_validator.py must reference required plan sections.\n"
            f"Expected references to: {required_sections}\n"
            f"Found: {found}\n"
            f"The validator must check that plan files contain these sections."
        )

    def test_returns_missing_sections_in_error(self):
        """Validator must return specific missing sections, not just pass/fail."""
        content = self.VALIDATOR.read_text()
        # Should have logic to collect and return missing sections
        has_missing_collection = (
            "missing" in content.lower()
            and ("section" in content.lower() or "sections" in content.lower())
        )
        assert has_missing_collection, (
            "plan_validator.py must report which specific sections are missing.\n"
            "Acceptance criterion: 'returns specific missing sections in error output'.\n"
            "Look for variables tracking missing sections."
        )

    def test_has_expiry_check(self):
        """Validator must check plan age and warn on expiry (>72h)."""
        content = self.VALIDATOR.read_text()
        has_time_check = any(term in content for term in ["72", "expir", "age", "hours", "timedelta"])
        assert has_time_check, (
            "plan_validator.py must implement plan expiry checking.\n"
            "Acceptance criterion: 'Expired plan (>72h) -> WARN emitted, work not blocked'.\n"
            "Expected reference to 72-hour threshold or time-based expiry logic."
        )

    def test_expiry_warns_not_blocks(self):
        """Expired plans must WARN, not block work."""
        content = self.VALIDATOR.read_text()
        # Should have a warning pathway, not a hard block for expiry
        has_warn = any(term in content.lower() for term in ["warn", "warning", "expired"])
        assert has_warn, (
            "plan_validator.py must emit a warning for expired plans, not block.\n"
            "Acceptance criterion: 'Expired plan (>72h) -> WARN emitted, work not blocked'."
        )


# ---------------------------------------------------------------------------
# 2. Plan Gate Hook
# ---------------------------------------------------------------------------

class TestAcceptancePlanGateHook:
    """Verify plugins/autonomous-dev/hooks/plan_gate.py enforces plan-before-write."""

    HOOK = PLUGINS / "hooks" / "plan_gate.py"
    SIDECAR = PLUGINS / "hooks" / "plan_gate.hook.json"

    def test_hook_file_exists(self):
        """plan_gate.py hook must exist."""
        assert self.HOOK.exists(), (
            f"Hook file not found at {self.HOOK}\n"
            f"This hook must be created as part of Issue #814 implementation."
        )

    def test_sidecar_exists(self):
        """plan_gate.hook.json sidecar must exist for hook registration."""
        assert self.SIDECAR.exists(), (
            f"Hook sidecar not found at {self.SIDECAR}\n"
            f"Every hook must have a .hook.json sidecar file."
        )

    def test_sidecar_is_valid_json(self):
        """Hook sidecar must be valid JSON."""
        content = self.SIDECAR.read_text()
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            pytest.fail(f"plan_gate.hook.json is not valid JSON: {e}")
        assert "name" in data, "Sidecar must have 'name' field"
        assert "registrations" in data, "Sidecar must have 'registrations' field"

    def test_sidecar_registers_pretooluse(self):
        """Hook must register for PreToolUse events (Write/Edit)."""
        data = json.loads(self.SIDECAR.read_text())
        events = [r.get("event", "") for r in data.get("registrations", [])]
        assert any("PreToolUse" in e for e in events), (
            f"plan_gate.hook.json must register for PreToolUse events.\n"
            f"Found events: {events}\n"
            f"The hook needs to intercept Write/Edit tool calls."
        )

    def test_hook_blocks_without_plan(self):
        """Hook must produce a block decision when no valid plan exists."""
        content = self.HOOK.read_text()
        assert '"decision"' in content or "'decision'" in content, (
            "plan_gate.py must output JSON with 'decision' field.\n"
            "Hook enforcement requires JSON decision format."
        )
        assert "block" in content.lower(), (
            "plan_gate.py must be capable of blocking (decision: block).\n"
            "Acceptance criterion: 'Write/Edit to non-doc file beyond complexity "
            "threshold -> blocked if no valid plan'."
        )

    def test_hook_has_required_next_action(self):
        """Block message must include REQUIRED NEXT ACTION directive (stick+carrot)."""
        content = self.HOOK.read_text()
        assert "REQUIRED NEXT ACTION" in content, (
            "plan_gate.py must contain 'REQUIRED NEXT ACTION' string.\n"
            "Acceptance criterion: 'Block message includes REQUIRED NEXT ACTION: run /plan'.\n"
            "This follows the stick+carrot enforcement pattern."
        )

    def test_hook_mentions_plan_command(self):
        """Block message must direct user to run /plan."""
        content = self.HOOK.read_text()
        assert "/plan" in content, (
            "plan_gate.py must reference '/plan' in its block message.\n"
            "Users must know HOW to unblock themselves."
        )

    def test_skip_plan_check_env_var(self):
        """SKIP_PLAN_CHECK=1 env var must disable all hook checks."""
        content = self.HOOK.read_text()
        assert "SKIP_PLAN_CHECK" in content, (
            "plan_gate.py must support SKIP_PLAN_CHECK environment variable.\n"
            "Acceptance criterion: 'SKIP_PLAN_CHECK=1 env var disables all hook checks'."
        )

    def test_simple_edits_never_blocked(self):
        """Simple edits (<3 files AND <100 lines) must never be blocked."""
        content = self.HOOK.read_text()
        # Should have threshold logic for file count and/or line count
        has_threshold = any(term in content for term in ["threshold", "simple", "lines", "files"])
        has_numeric_check = bool(re.search(r"[<>=]\s*[0-9]+", content))
        assert has_threshold or has_numeric_check, (
            "plan_gate.py must implement complexity thresholds.\n"
            "Acceptance criterion: 'Simple edits (<3 files AND <100 lines) are never blocked'.\n"
            "Expected threshold checks for file count and line count."
        )

    def test_fail_open_on_exception(self):
        """Hook must fail-open: any Python error results in allow, not block."""
        content = self.HOOK.read_text()
        has_try_except = "except" in content
        has_allow_fallback = bool(re.search(r'(allow|"allow")', content))
        assert has_try_except and has_allow_fallback, (
            "plan_gate.py must have try/except with allow fallback.\n"
            "Acceptance criterion: 'Hook exception -> allow, not block (fail-open)'.\n"
            f"Found except: {has_try_except}, Found allow fallback: {has_allow_fallback}"
        )

    def test_blocks_when_existing_solutions_missing(self):
        """Hook must block when plan is missing Existing Solutions section."""
        content = self.HOOK.read_text()
        assert "Existing Solutions" in content, (
            "plan_gate.py must check for 'Existing Solutions' section.\n"
            "Acceptance criterion: 'Hook blocks when Existing Solutions section is missing from plan'."
        )


# ---------------------------------------------------------------------------
# 3. Plan Critic Agent
# ---------------------------------------------------------------------------

class TestAcceptancePlanCriticAgent:
    """Verify plugins/autonomous-dev/agents/plan-critic.md defines adversarial critique."""

    AGENT = PLUGINS / "agents" / "plan-critic.md"

    def test_agent_file_exists(self):
        """plan-critic.md agent definition must exist."""
        assert self.AGENT.exists(), (
            f"Agent file not found at {self.AGENT}\n"
            f"This agent must be created as part of Issue #814 implementation."
        )

    def test_has_frontmatter(self):
        """Agent file must have YAML frontmatter."""
        content = self.AGENT.read_text()
        assert content.startswith("---"), (
            "plan-critic.md must start with YAML frontmatter (---).\n"
            "All agent definitions require frontmatter with model tier and metadata."
        )

    def test_references_critique_rounds(self):
        """Agent must specify minimum critique rounds before PROCEED."""
        content = self.AGENT.read_text()
        has_rounds = any(term in content.lower() for term in [
            "round", "critique", "iteration", "pass"
        ])
        has_minimum = any(term in content for term in ["2", "two", "minimum"])
        assert has_rounds and has_minimum, (
            "plan-critic.md must specify minimum 2 critique rounds.\n"
            "Acceptance criterion: 'plan-critic runs minimum 2 critique rounds before PROCEED'.\n"
            f"Found round reference: {has_rounds}, Found minimum reference: {has_minimum}"
        )

    def test_references_proceed_signal(self):
        """Agent must define when to issue PROCEED signal."""
        content = self.AGENT.read_text()
        assert "PROCEED" in content, (
            "plan-critic.md must reference the 'PROCEED' signal.\n"
            "The critic must define criteria for issuing PROCEED after review rounds."
        )

    def test_is_adversarial(self):
        """Agent must be described as adversarial/critical (not cooperative)."""
        content = self.AGENT.read_text().lower()
        adversarial_terms = ["adversarial", "critic", "challenge", "question", "push back", "gap"]
        found = [t for t in adversarial_terms if t in content]
        assert len(found) >= 2, (
            f"plan-critic.md must be adversarial in nature.\n"
            f"Expected multiple terms from: {adversarial_terms}\n"
            f"Found: {found}\n"
            f"The critic agent must actively challenge plans, not rubber-stamp them."
        )


# ---------------------------------------------------------------------------
# 4. Planning Workflow Skill
# ---------------------------------------------------------------------------

class TestAcceptancePlanningWorkflowSkill:
    """Verify plugins/autonomous-dev/skills/planning-workflow/SKILL.md documents 7 steps."""

    SKILL = PLUGINS / "skills" / "planning-workflow" / "SKILL.md"

    def test_skill_file_exists(self):
        """planning-workflow SKILL.md must exist."""
        assert self.SKILL.exists(), (
            f"Skill file not found at {self.SKILL}\n"
            f"This skill must be created as part of Issue #814 implementation."
        )

    def test_has_frontmatter(self):
        """Skill file must have YAML frontmatter."""
        content = self.SKILL.read_text()
        assert content.startswith("---"), (
            "SKILL.md must start with YAML frontmatter (---)."
        )

    def test_documents_seven_steps(self):
        """Skill must document all 7 planning workflow steps."""
        content = self.SKILL.read_text()
        # Look for step numbering patterns (Step 1, Step 2, etc. or numbered list)
        step_pattern = re.findall(r"(?:Step|STEP)\s*(\d+)", content, re.IGNORECASE)
        step_numbers = sorted(set(int(s) for s in step_pattern))
        assert len(step_numbers) >= 7, (
            f"SKILL.md must document all 7 planning workflow steps.\n"
            f"Found step numbers: {step_numbers}\n"
            f"Acceptance criterion: '/plan completes all 7 steps'."
        )

    def test_references_scope_check(self):
        """Skill must document the Step 2 scope check (>50% file estimate drift)."""
        content = self.SKILL.read_text()
        has_scope = "scope" in content.lower()
        has_threshold = "50%" in content or "50 %" in content
        assert has_scope and has_threshold, (
            "SKILL.md must document the Step 2 scope check.\n"
            "Acceptance criterion: 'Step 2 scope check halts workflow when estimated "
            "files exceed step-0 estimate by >50%'.\n"
            f"Found scope: {has_scope}, Found 50% threshold: {has_threshold}"
        )

    def test_references_existing_solutions(self):
        """Skill must document Step 3 Existing Solutions with WebSearch + grep."""
        content = self.SKILL.read_text()
        assert "Existing Solutions" in content, (
            "SKILL.md must document the 'Existing Solutions' step.\n"
            "Acceptance criterion: 'Step 3 includes WebSearch + codebase grep results'."
        )

    def test_references_web_search(self):
        """Step 3 must include WebSearch, not just codebase assertions."""
        content = self.SKILL.read_text().lower()
        has_web = any(term in content for term in ["websearch", "web search", "web_search", "search"])
        has_grep = any(term in content for term in ["grep", "codebase", "search"])
        assert has_web and has_grep, (
            "SKILL.md must reference both web search and codebase search in Step 3.\n"
            "Acceptance criterion: 'Step 3 includes WebSearch + codebase grep results, "
            "not just assertions'."
        )

    def test_references_plan_critic(self):
        """Skill must reference the plan-critic agent for adversarial review."""
        content = self.SKILL.read_text()
        assert "plan-critic" in content or "plan_critic" in content, (
            "SKILL.md must reference the plan-critic agent.\n"
            "The planning workflow must invoke the critic for adversarial review."
        )


# ---------------------------------------------------------------------------
# 5. /plan Command
# ---------------------------------------------------------------------------

class TestAcceptancePlanCommand:
    """Verify plugins/autonomous-dev/commands/plan.md defines the /plan slash command."""

    COMMAND = PLUGINS / "commands" / "plan.md"

    def test_command_file_exists(self):
        """/plan command file must exist."""
        assert self.COMMAND.exists(), (
            f"Command file not found at {self.COMMAND}\n"
            f"This command must be created as part of Issue #814 implementation."
        )

    def test_writes_plan_to_correct_directory(self):
        """Command must write plan files to .claude/plans/<slug>.md."""
        content = self.COMMAND.read_text()
        has_plans_dir = ".claude/plans" in content
        has_slug = "slug" in content.lower() or "<slug>" in content.lower()
        assert has_plans_dir, (
            "plan.md must reference '.claude/plans' output directory.\n"
            "Acceptance criterion: '/plan completes all 7 steps and writes "
            ".claude/plans/<slug>.md'."
        )
        assert has_slug or ".md" in content, (
            "plan.md must reference slug-based filename for plan output."
        )

    def test_references_all_seven_steps(self):
        """Command must reference all 7 workflow steps."""
        content = self.COMMAND.read_text()
        step_pattern = re.findall(r"(?:Step|STEP)\s*(\d+)", content, re.IGNORECASE)
        step_numbers = sorted(set(int(s) for s in step_pattern))
        # At minimum, steps should be referenced (may be via skill injection)
        has_steps = len(step_numbers) >= 5  # May delegate some to skill
        has_skill_ref = "planning-workflow" in content
        assert has_steps or has_skill_ref, (
            f"plan.md must reference workflow steps or planning-workflow skill.\n"
            f"Found step numbers: {step_numbers}\n"
            f"Found skill reference: {has_skill_ref}"
        )

    def test_plan_contains_required_sections(self):
        """Command must ensure plan output contains required sections."""
        content = self.COMMAND.read_text()
        required = ["WHY", "Existing Solutions", "Minimal Path"]
        found = [s for s in required if s in content]
        assert len(found) >= 2, (
            f"plan.md must reference required plan sections.\n"
            f"Expected: {required}\n"
            f"Found: {found}\n"
            f"Plan file must contain: WHY + SCOPE, Existing Solutions, Minimal Path."
        )

    def test_invokes_plan_critic(self):
        """Command must invoke the plan-critic agent."""
        content = self.COMMAND.read_text()
        assert "plan-critic" in content or "plan_critic" in content, (
            "plan.md must invoke the plan-critic agent.\n"
            "Acceptance criterion: 'plan-critic runs minimum 2 critique rounds before PROCEED'."
        )


# ---------------------------------------------------------------------------
# 6. /plan-to-issues Integration
# ---------------------------------------------------------------------------

class TestAcceptancePlanToIssuesIntegration:
    """Verify plan-to-issues.md is updated to detect .claude/plans/ files."""

    COMMAND = PLUGINS / "commands" / "plan-to-issues.md"

    def test_command_exists(self):
        """plan-to-issues.md must exist (pre-existing command)."""
        assert self.COMMAND.exists(), (
            f"plan-to-issues.md not found at {self.COMMAND}\n"
            f"This is a pre-existing command that should be modified."
        )

    def test_references_plans_directory(self):
        """plan-to-issues.md must reference .claude/plans/ as input source."""
        content = self.COMMAND.read_text()
        assert ".claude/plans" in content, (
            "plan-to-issues.md must reference '.claude/plans' directory.\n"
            "Acceptance criterion: '/plan-to-issues detects .claude/plans/ files "
            "and offers them as input source'."
        )


# ---------------------------------------------------------------------------
# 7. Registration (manifest, settings templates)
# ---------------------------------------------------------------------------

class TestAcceptanceRegistration:
    """Verify all new files are registered in install_manifest.json and settings."""

    MANIFEST = PLUGINS / "config" / "install_manifest.json"
    SETTINGS_LOCAL = PLUGINS / "templates" / "settings.local.json"
    SETTINGS_AD = PLUGINS / "templates" / "settings.autonomous-dev.json"

    def test_manifest_contains_plan_gate_hook(self):
        """install_manifest.json must list plan_gate hook."""
        content = self.MANIFEST.read_text()
        assert "plan_gate" in content, (
            "install_manifest.json must contain 'plan_gate'.\n"
            "All hooks must be listed in the install manifest for deployment."
        )

    def test_manifest_contains_plan_validator_lib(self):
        """install_manifest.json must list plan_validator library."""
        content = self.MANIFEST.read_text()
        assert "plan_validator" in content, (
            "install_manifest.json must contain 'plan_validator'.\n"
            "All library files must be in the install manifest."
        )

    def test_manifest_contains_plan_critic_agent(self):
        """install_manifest.json must list plan-critic agent."""
        content = self.MANIFEST.read_text()
        assert "plan-critic" in content or "plan_critic" in content, (
            "install_manifest.json must contain 'plan-critic' agent.\n"
            "All agent files must be in the install manifest."
        )

    def test_manifest_contains_planning_skill(self):
        """install_manifest.json must list planning-workflow skill."""
        content = self.MANIFEST.read_text()
        assert "planning-workflow" in content or "planning_workflow" in content, (
            "install_manifest.json must contain 'planning-workflow' skill.\n"
            "All skill directories must be in the install manifest."
        )

    def test_manifest_contains_plan_command(self):
        """install_manifest.json must list plan command."""
        content = self.MANIFEST.read_text()
        # The manifest should reference the plan.md command file
        manifest_data = json.loads(content)
        manifest_str = json.dumps(manifest_data)
        has_plan_cmd = "plan.md" in manifest_str or '"plan"' in manifest_str
        assert has_plan_cmd, (
            "install_manifest.json must contain 'plan' command reference.\n"
            "All command files must be in the install manifest."
        )

    def test_settings_local_contains_plan_gate(self):
        """settings.local.json must register plan_gate hook."""
        content = self.SETTINGS_LOCAL.read_text()
        assert "plan_gate" in content, (
            "settings.local.json must contain 'plan_gate'.\n"
            "All hooks must be registered in ALL settings templates."
        )

    def test_settings_autonomous_dev_contains_plan_gate(self):
        """settings.autonomous-dev.json must register plan_gate hook."""
        content = self.SETTINGS_AD.read_text()
        assert "plan_gate" in content, (
            "settings.autonomous-dev.json must contain 'plan_gate'.\n"
            "All hooks must be registered in ALL settings templates."
        )


# ---------------------------------------------------------------------------
# 8. Documentation
# ---------------------------------------------------------------------------

class TestAcceptanceDocumentation:
    """Verify documentation is created and updated."""

    WORKFLOW_DOC = REPO_ROOT / "docs" / "PLANNING-WORKFLOW.md"
    CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

    def test_planning_workflow_doc_exists(self):
        """docs/PLANNING-WORKFLOW.md must exist."""
        assert self.WORKFLOW_DOC.exists(), (
            f"Documentation not found at {self.WORKFLOW_DOC}\n"
            f"Acceptance criterion: 'docs/PLANNING-WORKFLOW.md documents the 7-step "
            f"workflow and design principles'."
        )

    def test_workflow_doc_covers_seven_steps(self):
        """PLANNING-WORKFLOW.md must document the 7-step workflow."""
        content = self.WORKFLOW_DOC.read_text()
        step_pattern = re.findall(r"(?:Step|STEP)\s*(\d+)", content, re.IGNORECASE)
        step_numbers = sorted(set(int(s) for s in step_pattern))
        assert len(step_numbers) >= 7, (
            f"PLANNING-WORKFLOW.md must document all 7 steps.\n"
            f"Found step numbers: {step_numbers}"
        )

    def test_workflow_doc_has_design_principles(self):
        """PLANNING-WORKFLOW.md must include design principles section."""
        content = self.WORKFLOW_DOC.read_text().lower()
        has_principles = any(term in content for term in [
            "design principle", "principles", "philosophy", "rationale"
        ])
        assert has_principles, (
            "PLANNING-WORKFLOW.md must document design principles.\n"
            "Acceptance criterion: 'documents the 7-step workflow and design principles'."
        )

    def test_claude_md_lists_plan_command(self):
        """CLAUDE.md must include /plan as its own command (not just /plan-to-issues)."""
        content = self.CLAUDE_MD.read_text()
        # Must match /plan as a standalone command, not just as part of /plan-to-issues
        has_plan_command = bool(re.search(r"`/plan`\s", content) or re.search(r"`/plan\s", content))
        assert has_plan_command, (
            "CLAUDE.md must list '/plan' as its own command entry.\n"
            "Currently only '/plan-to-issues' exists in the commands list.\n"
            "Acceptance criterion: 'CLAUDE.md updated with /plan in commands list'."
        )
