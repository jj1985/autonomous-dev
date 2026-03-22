"""TDD tests for hook sidecar metadata schema (.hook.json).

Issue #551: Define .hook.json sidecar metadata schema.

These tests validate the JSON Schema at:
    plugins/autonomous-dev/config/hook-metadata.schema.json

The schema describes a hook's metadata sidecar with:
- Two hook types: "lifecycle" (registered with Claude Code events) and "utility" (deployed but not registered)
- Registrations array: required for lifecycle hooks (event, matcher, timeout)
- Env vars: object mapping env var names to defaults
- Interpreter: enum "python3" or "bash"
- Conditional: lifecycle requires registrations; utility must have no registrations

Tests are structured as TDD red phase -- the schema does not exist yet, so all tests
will initially fail with FileNotFoundError until the schema is implemented.
"""

import json
import pytest
from pathlib import Path

try:
    from jsonschema import validate, ValidationError, Draft202012Validator
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WORKTREE = Path("/Users/andrewkaszubski/Dev/autonomous-dev/.worktrees/batch-20260322-180033")
SCHEMA_PATH = WORKTREE / "plugins" / "autonomous-dev" / "config" / "hook-metadata.schema.json"
HOOKS_DIR = WORKTREE / "plugins" / "autonomous-dev" / "hooks"

# Canonical lifecycle event names from Claude Code hook system
VALID_LIFECYCLE_EVENTS = [
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "SubagentStop",
    "TaskCompleted",
    "PreCompact",
    "PostCompact",
    "SessionStart",
]

pytestmark = pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def schema():
    """Load the hook-metadata JSON Schema from disk."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)


@pytest.fixture
def validator(schema):
    """Return a Draft202012 validator instance for reuse."""
    return Draft202012Validator(schema)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validates(instance: dict, schema: dict) -> bool:
    """Return True if instance validates against schema, False otherwise."""
    try:
        validate(instance=instance, schema=schema, cls=Draft202012Validator)
        return True
    except ValidationError:
        return False


def _validation_error(instance: dict, schema: dict) -> str:
    """Return the validation error message, or empty string if valid."""
    try:
        validate(instance=instance, schema=schema, cls=Draft202012Validator)
        return ""
    except ValidationError as e:
        return e.message


def _minimal_lifecycle() -> dict:
    """Return a minimal valid lifecycle hook sidecar."""
    return {
        "name": "my_hook",
        "type": "lifecycle",
        "interpreter": "python3",
        "registrations": [
            {
                "event": "PreToolUse",
            }
        ],
    }


def _minimal_utility() -> dict:
    """Return a minimal valid utility hook sidecar."""
    return {
        "name": "my_util",
        "type": "utility",
        "interpreter": "python3",
    }


# ===========================================================================
# POSITIVE TESTS -- valid schemas
# ===========================================================================

class TestValidSchemas:
    """Positive validation: these instances MUST be accepted by the schema."""

    def test_lifecycle_single_registration(self, schema):
        """A lifecycle hook with one registration (e.g. unified_prompt_validator)."""
        instance = {
            "name": "unified_prompt_validator",
            "type": "lifecycle",
            "interpreter": "python3",
            "registrations": [
                {
                    "event": "UserPromptSubmit",
                    "matcher": "*",
                    "timeout": 10,
                }
            ],
        }
        assert _validates(instance, schema), _validation_error(instance, schema)

    def test_lifecycle_multiple_registrations(self, schema):
        """A lifecycle hook with multiple registrations (e.g. session_activity_logger)."""
        instance = {
            "name": "session_activity_logger",
            "type": "lifecycle",
            "interpreter": "python3",
            "registrations": [
                {
                    "event": "PostToolUse",
                    "matcher": "*",
                    "timeout": 5,
                },
                {
                    "event": "Stop",
                    "timeout": 5,
                },
            ],
        }
        assert _validates(instance, schema), _validation_error(instance, schema)

    def test_lifecycle_with_env_vars(self, schema):
        """A lifecycle hook with env vars (e.g. unified_pre_tool)."""
        instance = {
            "name": "unified_pre_tool",
            "type": "lifecycle",
            "interpreter": "python3",
            "registrations": [
                {
                    "event": "PreToolUse",
                    "matcher": "Write|Edit|MultiEdit",
                    "timeout": 10,
                }
            ],
            "env": {
                "IMPLEMENT_PIPELINE_ACTIVE": "false",
                "AUTO_GIT_ENABLED": "false",
            },
        }
        assert _validates(instance, schema), _validation_error(instance, schema)

    def test_utility_no_registrations(self, schema):
        """A utility file (e.g. genai_utils) with no registrations."""
        instance = {
            "name": "genai_utils",
            "type": "utility",
            "interpreter": "python3",
        }
        assert _validates(instance, schema), _validation_error(instance, schema)

    def test_bash_interpreter(self, schema):
        """A .sh hook with interpreter='bash'."""
        instance = {
            "name": "SessionStart-batch-recovery",
            "type": "lifecycle",
            "interpreter": "bash",
            "registrations": [
                {
                    "event": "SessionStart",
                    "timeout": 15,
                }
            ],
        }
        assert _validates(instance, schema), _validation_error(instance, schema)

    def test_minimal_lifecycle_fields_only(self, schema):
        """Minimal lifecycle hook -- only required fields, no optional ones."""
        instance = _minimal_lifecycle()
        assert _validates(instance, schema), _validation_error(instance, schema)

    def test_minimal_utility_fields_only(self, schema):
        """Minimal utility hook -- only required fields."""
        instance = _minimal_utility()
        assert _validates(instance, schema), _validation_error(instance, schema)

    @pytest.mark.parametrize("event", VALID_LIFECYCLE_EVENTS)
    def test_all_valid_lifecycle_events_accepted(self, schema, event):
        """Every canonical lifecycle event name must be accepted."""
        instance = _minimal_lifecycle()
        instance["registrations"][0]["event"] = event
        assert _validates(instance, schema), (
            f"Event '{event}' should be valid but was rejected: "
            f"{_validation_error(instance, schema)}"
        )

    def test_registration_default_matcher(self, schema):
        """Registration without explicit matcher should be valid (matcher is optional with default)."""
        instance = {
            "name": "test_hook",
            "type": "lifecycle",
            "interpreter": "python3",
            "registrations": [
                {
                    "event": "PreToolUse",
                    # no matcher -- should default to "*"
                }
            ],
        }
        assert _validates(instance, schema), _validation_error(instance, schema)

    def test_registration_default_timeout(self, schema):
        """Registration without explicit timeout should be valid (timeout is optional with default)."""
        instance = {
            "name": "test_hook",
            "type": "lifecycle",
            "interpreter": "python3",
            "registrations": [
                {
                    "event": "PostToolUse",
                    # no timeout -- should use default
                }
            ],
        }
        assert _validates(instance, schema), _validation_error(instance, schema)

    def test_timeout_boundary_min(self, schema):
        """Timeout of 1 (minimum) should be valid."""
        instance = _minimal_lifecycle()
        instance["registrations"][0]["timeout"] = 1
        assert _validates(instance, schema), _validation_error(instance, schema)

    def test_timeout_boundary_max(self, schema):
        """Timeout of 60 (maximum) should be valid."""
        instance = _minimal_lifecycle()
        instance["registrations"][0]["timeout"] = 60
        assert _validates(instance, schema), _validation_error(instance, schema)

    def test_description_field(self, schema):
        """A hook with an optional description field should validate."""
        instance = _minimal_lifecycle()
        instance["description"] = "Validates prompt submissions for pipeline compliance"
        assert _validates(instance, schema), _validation_error(instance, schema)


# ===========================================================================
# NEGATIVE TESTS -- invalid schemas that MUST be rejected
# ===========================================================================

class TestInvalidSchemas:
    """Negative validation: these instances MUST be rejected by the schema."""

    def test_missing_required_name(self, schema):
        """Missing 'name' field must fail."""
        instance = {
            "type": "lifecycle",
            "interpreter": "python3",
            "registrations": [{"event": "PreToolUse"}],
        }
        assert not _validates(instance, schema), "Should reject missing 'name'"

    def test_missing_required_type(self, schema):
        """Missing 'type' field must fail."""
        instance = {
            "name": "my_hook",
            "interpreter": "python3",
            "registrations": [{"event": "PreToolUse"}],
        }
        assert not _validates(instance, schema), "Should reject missing 'type'"

    def test_missing_required_interpreter(self, schema):
        """Missing 'interpreter' field must fail."""
        instance = {
            "name": "my_hook",
            "type": "lifecycle",
            "registrations": [{"event": "PreToolUse"}],
        }
        assert not _validates(instance, schema), "Should reject missing 'interpreter'"

    def test_invalid_type_value(self, schema):
        """Type must be 'lifecycle' or 'utility', not arbitrary string."""
        instance = _minimal_lifecycle()
        instance["type"] = "daemon"
        assert not _validates(instance, schema), "Should reject invalid type 'daemon'"

    def test_invalid_lifecycle_event(self, schema):
        """Invalid lifecycle event name must be rejected."""
        instance = _minimal_lifecycle()
        instance["registrations"][0]["event"] = "InvalidEvent"
        assert not _validates(instance, schema), "Should reject invalid event 'InvalidEvent'"

    def test_invalid_lifecycle_event_case_sensitive(self, schema):
        """Event names are case-sensitive -- lowercase must fail."""
        instance = _minimal_lifecycle()
        instance["registrations"][0]["event"] = "pretooluse"
        assert not _validates(instance, schema), (
            "Should reject lowercase event name 'pretooluse'"
        )

    @pytest.mark.parametrize("bad_timeout", [0, -1, 61, 100, -10, 999])
    def test_timeout_out_of_range(self, schema, bad_timeout):
        """Timeout outside 1-60 range must fail."""
        instance = _minimal_lifecycle()
        instance["registrations"][0]["timeout"] = bad_timeout
        assert not _validates(instance, schema), (
            f"Should reject timeout={bad_timeout}"
        )

    def test_timeout_as_string(self, schema):
        """Timeout must be integer, not string."""
        instance = _minimal_lifecycle()
        instance["registrations"][0]["timeout"] = "10"
        assert not _validates(instance, schema), "Should reject string timeout"

    def test_timeout_as_float(self, schema):
        """Timeout must be integer, not float."""
        instance = _minimal_lifecycle()
        instance["registrations"][0]["timeout"] = 10.5
        assert not _validates(instance, schema), "Should reject float timeout"

    def test_lifecycle_with_no_registrations(self, schema):
        """Lifecycle hook with no registrations must fail (conditional requirement)."""
        instance = {
            "name": "bad_hook",
            "type": "lifecycle",
            "interpreter": "python3",
            # No registrations at all
        }
        assert not _validates(instance, schema), (
            "Lifecycle hook without registrations should be rejected"
        )

    def test_lifecycle_with_empty_registrations(self, schema):
        """Lifecycle hook with empty registrations array must fail."""
        instance = {
            "name": "bad_hook",
            "type": "lifecycle",
            "interpreter": "python3",
            "registrations": [],
        }
        assert not _validates(instance, schema), (
            "Lifecycle hook with empty registrations should be rejected"
        )

    def test_invalid_interpreter(self, schema):
        """Invalid interpreter value must fail."""
        instance = _minimal_lifecycle()
        instance["interpreter"] = "ruby"
        assert not _validates(instance, schema), "Should reject invalid interpreter 'ruby'"

    def test_extra_unknown_fields_at_root(self, schema):
        """Unknown fields at root level must fail (additionalProperties: false)."""
        instance = _minimal_lifecycle()
        instance["unknown_field"] = "surprise"
        assert not _validates(instance, schema), (
            "Should reject unknown root-level field 'unknown_field'"
        )

    def test_registration_missing_event(self, schema):
        """Registration without 'event' must fail (event is required in registration)."""
        instance = {
            "name": "bad_hook",
            "type": "lifecycle",
            "interpreter": "python3",
            "registrations": [
                {"matcher": "*", "timeout": 10}
                # Missing 'event'
            ],
        }
        assert not _validates(instance, schema), (
            "Registration without 'event' should be rejected"
        )

    def test_name_empty_string(self, schema):
        """Empty string for name should fail (minLength or pattern constraint)."""
        instance = _minimal_lifecycle()
        instance["name"] = ""
        assert not _validates(instance, schema), "Should reject empty name"

    def test_env_value_not_string(self, schema):
        """Env var values must be strings, not integers."""
        instance = _minimal_lifecycle()
        instance["env"] = {"SOME_VAR": 123}
        assert not _validates(instance, schema), (
            "Env var values must be strings, not integers"
        )

    def test_type_null(self, schema):
        """Null type must fail."""
        instance = _minimal_lifecycle()
        instance["type"] = None
        assert not _validates(instance, schema), "Should reject null type"

    def test_registrations_not_array(self, schema):
        """Registrations must be an array, not an object."""
        instance = {
            "name": "bad_hook",
            "type": "lifecycle",
            "interpreter": "python3",
            "registrations": {"event": "PreToolUse"},
        }
        assert not _validates(instance, schema), (
            "Registrations must be an array, not an object"
        )


# ===========================================================================
# CONDITIONAL LOGIC TESTS
# ===========================================================================

class TestConditionalLogic:
    """Tests for the if/then/else conditional: lifecycle requires registrations,
    utility must not have registrations."""

    def test_utility_with_registrations_rejected(self, schema):
        """Utility hook must NOT have registrations (should fail conditional)."""
        instance = {
            "name": "bad_util",
            "type": "utility",
            "interpreter": "python3",
            "registrations": [
                {"event": "PreToolUse"}
            ],
        }
        assert not _validates(instance, schema), (
            "Utility hook with registrations should be rejected"
        )

    def test_utility_with_empty_registrations_rejected(self, schema):
        """Utility hook with empty registrations array should also be rejected
        (registrations field itself should be absent for utility)."""
        instance = {
            "name": "bad_util",
            "type": "utility",
            "interpreter": "python3",
            "registrations": [],
        }
        # Depending on schema design, this may or may not be rejected.
        # The planner says "registrations must be absent/empty" for utility.
        # If the schema allows empty array for utility, this test documents that.
        # We test the stricter interpretation: registrations should be absent entirely.
        # If the implementer chooses to allow empty array, this test can be adjusted.
        assert not _validates(instance, schema), (
            "Utility hook should not have registrations field at all"
        )

    def test_lifecycle_requires_at_least_one_registration(self, schema):
        """Lifecycle hook must have at least one registration (minItems: 1)."""
        instance = {
            "name": "my_hook",
            "type": "lifecycle",
            "interpreter": "python3",
            "registrations": [],
        }
        assert not _validates(instance, schema), (
            "Lifecycle hook needs at least one registration"
        )


# ===========================================================================
# SCHEMA STRUCTURAL TESTS
# ===========================================================================

class TestSchemaStructure:
    """Tests for the schema file itself -- existence, valid JSON, metadata fields."""

    def test_schema_file_exists(self):
        """The schema file must exist at the expected path."""
        assert SCHEMA_PATH.exists(), (
            f"Schema file not found at {SCHEMA_PATH}. "
            f"Create it at plugins/autonomous-dev/config/hook-metadata.schema.json"
        )

    def test_schema_is_valid_json(self):
        """The schema file must be valid JSON."""
        with open(SCHEMA_PATH) as f:
            data = json.load(f)
        assert isinstance(data, dict), "Schema must be a JSON object"

    def test_schema_has_json_schema_dialect(self, schema):
        """Schema should declare its JSON Schema dialect ($schema key)."""
        assert "$schema" in schema, (
            "Schema should declare $schema (e.g. https://json-schema.org/draft/2020-12/schema)"
        )

    def test_schema_type_is_object(self, schema):
        """Root type must be 'object'."""
        assert schema.get("type") == "object", "Root schema type must be 'object'"

    def test_schema_defines_required_fields(self, schema):
        """Schema must declare required fields."""
        required = schema.get("required", [])
        assert "name" in required, "'name' must be required"
        assert "type" in required, "'type' must be required"
        assert "interpreter" in required, "'interpreter' must be required"

    def test_schema_defines_type_enum(self, schema):
        """The 'type' property should be an enum with 'lifecycle' and 'utility'."""
        props = schema.get("properties", {})
        type_prop = props.get("type", {})
        enum_values = type_prop.get("enum", [])
        assert "lifecycle" in enum_values, "'lifecycle' must be in type enum"
        assert "utility" in enum_values, "'utility' must be in type enum"

    def test_schema_defines_interpreter_enum(self, schema):
        """The 'interpreter' property should include 'python3' and 'bash'."""
        props = schema.get("properties", {})
        interp_prop = props.get("interpreter", {})
        enum_values = interp_prop.get("enum", [])
        assert "python3" in enum_values, "'python3' must be in interpreter enum"
        assert "bash" in enum_values, "'bash' must be in interpreter enum"

    def test_schema_defines_registrations_property(self, schema):
        """Schema must define a 'registrations' property."""
        props = schema.get("properties", {})
        assert "registrations" in props, "Schema must define 'registrations' property"

    def test_schema_defines_env_property(self, schema):
        """Schema must define an 'env' property for environment variables."""
        props = schema.get("properties", {})
        assert "env" in props, "Schema must define 'env' property"

    def test_schema_has_conditional_logic(self, schema):
        """Schema must have if/then or allOf with conditional rules."""
        # The schema should use JSON Schema conditionals to enforce:
        #   - lifecycle requires registrations
        #   - utility forbids registrations
        has_if_then = "if" in schema
        has_allof = "allOf" in schema
        assert has_if_then or has_allof, (
            "Schema must define conditional logic (if/then or allOf) "
            "to enforce type-specific registration requirements"
        )


# ===========================================================================
# PROPERTY-BASED TESTS (hypothesis)
# ===========================================================================

try:
    from hypothesis import given, strategies as st, assume, settings as hyp_settings
    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False
    # Define no-op stubs so class body parses without NameError.
    # All methods return `self` to support chaining (e.g. st.text().filter()).
    def given(*args, **kwargs):  # noqa: E303
        def decorator(fn):
            return fn
        return decorator

    class _StubSt:
        """Chainable stub strategies module for when hypothesis is not installed."""
        def text(self, **kw): return self
        def integers(self, **kw): return self
        def sampled_from(self, vals): return self
        def one_of(self, *args): return self
        def dictionaries(self, **kw): return self
        def characters(self, **kw): return self
        def filter(self, fn): return self

    st = _StubSt()

    def hyp_settings(**kwargs):  # noqa: E303
        def decorator(fn):
            return fn
        return decorator


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestPropertyBased:
    """Property-based invariants using hypothesis."""

    @given(name=st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="_-"
    )))
    @hyp_settings(max_examples=20)
    def test_any_valid_name_accepted(self, schema, name):
        """Any non-empty alphanumeric+underscore name should be accepted."""
        instance = _minimal_lifecycle()
        instance["name"] = name
        assert _validates(instance, schema), (
            f"Name '{name}' should be accepted but was rejected: "
            f"{_validation_error(instance, schema)}"
        )

    @given(event=st.sampled_from(VALID_LIFECYCLE_EVENTS))
    @hyp_settings(max_examples=20)
    def test_any_valid_event_roundtrips(self, schema, event):
        """Any valid event should produce a valid lifecycle hook."""
        instance = _minimal_lifecycle()
        instance["registrations"][0]["event"] = event
        assert _validates(instance, schema)

    @given(timeout=st.integers(min_value=1, max_value=60))
    @hyp_settings(max_examples=20)
    def test_valid_timeout_range_always_accepted(self, schema, timeout):
        """Any integer in [1, 60] must be accepted as timeout."""
        instance = _minimal_lifecycle()
        instance["registrations"][0]["timeout"] = timeout
        assert _validates(instance, schema), (
            f"Timeout {timeout} should be valid but was rejected"
        )

    @given(timeout=st.one_of(
        st.integers(max_value=0),
        st.integers(min_value=61),
    ))
    @hyp_settings(max_examples=20)
    def test_invalid_timeout_range_always_rejected(self, schema, timeout):
        """Any integer outside [1, 60] must be rejected as timeout."""
        instance = _minimal_lifecycle()
        instance["registrations"][0]["timeout"] = timeout
        assert not _validates(instance, schema), (
            f"Timeout {timeout} should be invalid but was accepted"
        )

    @given(env=st.dictionaries(
        keys=st.text(min_size=1, max_size=30, alphabet=st.characters(
            whitelist_categories=("Lu",), whitelist_characters="_"
        )),
        values=st.text(min_size=0, max_size=50),
        min_size=0,
        max_size=5,
    ))
    @hyp_settings(max_examples=15)
    def test_env_with_string_values_always_valid(self, schema, env):
        """Env vars with string keys and string values must always validate."""
        instance = _minimal_lifecycle()
        instance["env"] = env
        assert _validates(instance, schema), (
            f"Env {env} should be valid but was rejected: "
            f"{_validation_error(instance, schema)}"
        )

    @given(bad_type=st.text(min_size=1).filter(
        lambda t: t not in ("lifecycle", "utility")
    ))
    @hyp_settings(max_examples=15)
    def test_arbitrary_type_values_rejected(self, schema, bad_type):
        """Any type value that is not 'lifecycle' or 'utility' must be rejected."""
        instance = _minimal_lifecycle()
        instance["type"] = bad_type
        assert not _validates(instance, schema), (
            f"Type '{bad_type}' should be invalid but was accepted"
        )


# ===========================================================================
# EXAMPLE SIDECAR VALIDATION (against real hook files)
# ===========================================================================

class TestExampleSidecars:
    """Validate that example .hook.json sidecars for known hooks would pass schema.

    These tests construct what the sidecar SHOULD look like for existing hooks,
    based on their known registrations. They serve as acceptance criteria for
    both the schema and the future sidecar files themselves.
    """

    def test_unified_pre_tool_sidecar(self, schema):
        """unified_pre_tool registers for PreToolUse with Write|Edit matcher."""
        instance = {
            "name": "unified_pre_tool",
            "type": "lifecycle",
            "interpreter": "python3",
            "registrations": [
                {
                    "event": "PreToolUse",
                    "matcher": "Write|Edit|MultiEdit",
                    "timeout": 10,
                }
            ],
            "env": {
                "IMPLEMENT_PIPELINE_ACTIVE": "false",
                "AUTO_GIT_ENABLED": "false",
            },
        }
        assert _validates(instance, schema), _validation_error(instance, schema)

    def test_session_activity_logger_sidecar(self, schema):
        """session_activity_logger registers for PostToolUse and Stop."""
        instance = {
            "name": "session_activity_logger",
            "type": "lifecycle",
            "interpreter": "python3",
            "registrations": [
                {
                    "event": "PostToolUse",
                    "matcher": "*",
                    "timeout": 5,
                },
                {
                    "event": "Stop",
                    "timeout": 5,
                },
            ],
        }
        assert _validates(instance, schema), _validation_error(instance, schema)

    def test_genai_utils_sidecar(self, schema):
        """genai_utils is a utility -- no registrations."""
        instance = {
            "name": "genai_utils",
            "type": "utility",
            "interpreter": "python3",
        }
        assert _validates(instance, schema), _validation_error(instance, schema)

    def test_session_start_bash_sidecar(self, schema):
        """SessionStart-batch-recovery.sh is a bash lifecycle hook."""
        instance = {
            "name": "SessionStart-batch-recovery",
            "type": "lifecycle",
            "interpreter": "bash",
            "registrations": [
                {
                    "event": "SessionStart",
                    "timeout": 15,
                }
            ],
        }
        assert _validates(instance, schema), _validation_error(instance, schema)

    def test_unified_prompt_validator_sidecar(self, schema):
        """unified_prompt_validator registers for UserPromptSubmit."""
        instance = {
            "name": "unified_prompt_validator",
            "type": "lifecycle",
            "interpreter": "python3",
            "registrations": [
                {
                    "event": "UserPromptSubmit",
                    "matcher": "*",
                    "timeout": 10,
                }
            ],
        }
        assert _validates(instance, schema), _validation_error(instance, schema)

    def test_stop_quality_gate_sidecar(self, schema):
        """stop_quality_gate registers for Stop event."""
        instance = {
            "name": "stop_quality_gate",
            "type": "lifecycle",
            "interpreter": "python3",
            "registrations": [
                {
                    "event": "Stop",
                    "timeout": 10,
                }
            ],
        }
        assert _validates(instance, schema), _validation_error(instance, schema)

    def test_task_completed_handler_sidecar(self, schema):
        """task_completed_handler registers for TaskCompleted event."""
        instance = {
            "name": "task_completed_handler",
            "type": "lifecycle",
            "interpreter": "python3",
            "registrations": [
                {
                    "event": "TaskCompleted",
                    "timeout": 10,
                }
            ],
        }
        assert _validates(instance, schema), _validation_error(instance, schema)


# ===========================================================================
# SIDECAR COVERAGE TESTS (Issue #554)
# ===========================================================================

class TestSidecarCoverage:
    """Verify every active hook has a .hook.json sidecar and each sidecar validates.

    Issue #554: Migrate all active hooks to .hook.json sidecar registration.
    These tests ensure no hook file is deployed without a corresponding sidecar,
    and every sidecar passes the JSON Schema.
    """

    def _get_hook_scripts(self) -> set[str]:
        """Return set of hook script stems (without extension) in HOOKS_DIR."""
        scripts = set()
        for path in HOOKS_DIR.iterdir():
            if path.is_file() and not path.name.startswith("__"):
                if path.suffix in (".py", ".sh") and "archived" not in path.parts:
                    scripts.add(path.stem)
        return scripts

    def _get_sidecar_names(self) -> set[str]:
        """Return set of sidecar names (from .hook.json filenames) in HOOKS_DIR."""
        sidecars = set()
        for path in HOOKS_DIR.glob("*.hook.json"):
            # filename like "foo.hook.json" -> stem is "foo.hook", we want "foo"
            sidecars.add(path.name.replace(".hook.json", ""))
        return sidecars

    def test_every_hook_has_sidecar(self):
        """Every .py/.sh hook script must have a corresponding .hook.json sidecar."""
        scripts = self._get_hook_scripts()
        sidecars = self._get_sidecar_names()
        missing = sorted(scripts - sidecars)
        assert not missing, (
            f"Hook scripts without .hook.json sidecars: {missing}\n"
            f"Create a sidecar for each: plugins/autonomous-dev/hooks/<name>.hook.json\n"
            f"See: plugins/autonomous-dev/config/hook-metadata.schema.json"
        )

    def test_every_sidecar_has_hook(self):
        """Every .hook.json sidecar must have a corresponding hook script."""
        scripts = self._get_hook_scripts()
        sidecars = self._get_sidecar_names()
        orphaned = sorted(sidecars - scripts)
        assert not orphaned, (
            f"Sidecar files without matching hook scripts: {orphaned}\n"
            f"Either create the hook or remove the orphaned sidecar"
        )

    def test_all_sidecars_valid_json(self):
        """Every .hook.json file must be parseable JSON."""
        for path in sorted(HOOKS_DIR.glob("*.hook.json")):
            with open(path) as f:
                data = json.load(f)
            assert isinstance(data, dict), f"{path.name} is not a JSON object"

    def test_all_sidecars_have_required_fields(self):
        """Every sidecar must contain name, type, and interpreter."""
        for path in sorted(HOOKS_DIR.glob("*.hook.json")):
            with open(path) as f:
                data = json.load(f)
            for field in ("name", "type", "interpreter"):
                assert field in data, (
                    f"{path.name} missing required field '{field}'"
                )

    def test_all_sidecars_validate_against_schema(self, schema):
        """Every .hook.json sidecar must pass the JSON Schema validation."""
        for path in sorted(HOOKS_DIR.glob("*.hook.json")):
            with open(path) as f:
                data = json.load(f)
            assert _validates(data, schema), (
                f"{path.name} failed schema validation: "
                f"{_validation_error(data, schema)}"
            )

    def test_sidecar_name_matches_filename(self):
        """The 'name' field in each sidecar must match its filename (minus .hook.json)."""
        for path in sorted(HOOKS_DIR.glob("*.hook.json")):
            expected_name = path.name.replace(".hook.json", "")
            with open(path) as f:
                data = json.load(f)
            assert data["name"] == expected_name, (
                f"{path.name}: 'name' field is '{data['name']}' "
                f"but expected '{expected_name}'"
            )

    def test_lifecycle_hooks_have_registrations(self):
        """All lifecycle sidecars must have non-empty registrations."""
        for path in sorted(HOOKS_DIR.glob("*.hook.json")):
            with open(path) as f:
                data = json.load(f)
            if data.get("type") == "lifecycle":
                regs = data.get("registrations", [])
                assert len(regs) >= 1, (
                    f"{path.name}: lifecycle hook must have at least one registration"
                )

    def test_utility_hooks_have_no_registrations(self):
        """All utility sidecars must NOT have registrations."""
        for path in sorted(HOOKS_DIR.glob("*.hook.json")):
            with open(path) as f:
                data = json.load(f)
            if data.get("type") == "utility":
                assert "registrations" not in data, (
                    f"{path.name}: utility hook must not have registrations"
                )

    def test_minimum_sidecar_count(self):
        """There must be at least 25 sidecar files (3 existing + 22 new)."""
        sidecars = list(HOOKS_DIR.glob("*.hook.json"))
        assert len(sidecars) >= 25, (
            f"Expected at least 25 sidecars, found {len(sidecars)}"
        )

    def test_interpreter_matches_file_extension(self):
        """Sidecar interpreter should match the actual hook file extension."""
        ext_map = {"python3": ".py", "bash": ".sh"}
        for path in sorted(HOOKS_DIR.glob("*.hook.json")):
            with open(path) as f:
                data = json.load(f)
            name = data["name"]
            interpreter = data["interpreter"]
            expected_ext = ext_map.get(interpreter, ".py")
            hook_file = HOOKS_DIR / f"{name}{expected_ext}"
            assert hook_file.exists(), (
                f"{path.name}: interpreter='{interpreter}' implies "
                f"hook file '{name}{expected_ext}' but it does not exist"
            )
