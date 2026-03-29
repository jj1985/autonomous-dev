"""Tests for detect_issue_research() -- Issue #628."""

import sys

sys.path.insert(0, "plugins/autonomous-dev/lib")

from research_persistence import detect_issue_research


THOROUGH_ISSUE_BODY = """\
## Summary

This feature adds JWT authentication to the API gateway.

## Implementation Approach

Use PyJWT library with RS256 signing. Integrate at the middleware layer
so all routes are protected by default.

## What Does NOT Work

- HS256 is insecure for multi-service architectures
- Cookie-based sessions don't scale across microservices

## Security Considerations

- Rotate signing keys every 90 days
- Store refresh tokens in HttpOnly cookies
- Validate audience and issuer claims

## Test Scenarios

1. Valid token passes authentication
2. Expired token returns 401
3. Malformed token returns 400

## Scenarios

- High traffic: 10k req/s token validation
- Key rotation during active sessions

## Acceptance Criteria

- [ ] All API routes require valid JWT
- [ ] Token refresh endpoint works
"""

QUICK_ISSUE_BODY = """\
## Summary

Add rate limiting to the API.

## Implementation Approach

Use a sliding window counter with Redis.

## Test Scenarios

1. Requests under limit pass
2. Requests over limit get 429

## Acceptance Criteria

- [ ] Rate limiting works
- [ ] Returns 429 when exceeded
"""


class TestDetectIssueResearch:
    """Tests for detect_issue_research function."""

    def test_thorough_issue_body_detected(self) -> None:
        """Full thorough issue body with 6+ sections is detected as research-rich."""
        result = detect_issue_research(THOROUGH_ISSUE_BODY)
        assert result["is_research_rich"] is True
        assert result["section_count"] >= 3

    def test_quick_issue_body_not_detected(self) -> None:
        """Quick issue body with only 2 research sections is not research-rich."""
        result = detect_issue_research(QUICK_ISSUE_BODY)
        assert result["is_research_rich"] is False
        # "Implementation Approach" and "Test Scenarios" are research sections
        # "Summary" and "Acceptance Criteria" are NOT
        assert result["section_count"] == 2

    def test_empty_body(self) -> None:
        """Empty string returns not research-rich with zero sections."""
        result = detect_issue_research("")
        assert result["is_research_rich"] is False
        assert result["section_count"] == 0
        assert result["matched_sections"] == []
        assert result["issue_body_as_research"] == ""

    def test_none_body(self) -> None:
        """None input is handled gracefully."""
        result = detect_issue_research(None)  # type: ignore[arg-type]
        assert result["is_research_rich"] is False
        assert result["section_count"] == 0

    def test_code_blocks_stripped(self) -> None:
        """H2 headings inside code blocks are NOT counted."""
        body = """\
## Summary

Some text.

```markdown
## Implementation Approach

This is inside a code block and should not match.

## Security Considerations

Also inside code block.

## Edge Cases

Also inside code block.
```

## Acceptance Criteria

- [ ] Something
"""
        result = detect_issue_research(body)
        # Only non-code-block headings: Summary (excluded), Acceptance Criteria (excluded)
        assert result["is_research_rich"] is False
        assert result["section_count"] == 0

    def test_boundary_exactly_three_sections(self) -> None:
        """Body with exactly 3 research sections is research-rich."""
        body = """\
## Implementation Approach

Use pattern X.

## Security Considerations

Validate all inputs.

## Edge Cases

Handle empty input.
"""
        result = detect_issue_research(body)
        assert result["is_research_rich"] is True
        assert result["section_count"] == 3

    def test_boundary_two_sections(self) -> None:
        """Body with exactly 2 research sections is NOT research-rich."""
        body = """\
## Implementation Approach

Use pattern X.

## Security Considerations

Validate all inputs.
"""
        result = detect_issue_research(body)
        assert result["is_research_rich"] is False
        assert result["section_count"] == 2

    def test_case_insensitive_matching(self) -> None:
        """Headings are matched case-insensitively."""
        body = """\
## implementation approach

Use pattern X.

## security considerations

Validate inputs.

## edge cases

Handle empty input.
"""
        result = detect_issue_research(body)
        assert result["is_research_rich"] is True
        assert result["section_count"] == 3

    def test_matched_sections_list(self) -> None:
        """matched_sections contains the correct section names."""
        body = """\
## Implementation Approach

Details here.

## Dependencies

Library X, Library Y.

## Background

Historical context.
"""
        result = detect_issue_research(body)
        assert "Implementation Approach" in result["matched_sections"]
        assert "Dependencies" in result["matched_sections"]
        assert "Background" in result["matched_sections"]
        assert result["section_count"] == 3

    def test_issue_body_as_research_contains_content(self) -> None:
        """issue_body_as_research contains actual section content, not just headers."""
        body = """\
## Implementation Approach

Use the decorator pattern for middleware.

## Dependencies

- PyJWT >= 2.0
- cryptography >= 41.0

## Background

The current system uses session cookies.
"""
        result = detect_issue_research(body)
        research = result["issue_body_as_research"]
        assert "## Implementation Approach" in research
        assert "decorator pattern" in research
        assert "## Dependencies" in research
        assert "PyJWT" in research
        assert "## Background" in research
        assert "session cookies" in research

    def test_empty_sections_not_counted(self) -> None:
        """H2 headers with no content under them are NOT counted."""
        body = """\
## Implementation Approach

## Security Considerations

## Edge Cases

## Background

Actual content here.
"""
        result = detect_issue_research(body)
        # Only "Background" has content
        assert result["section_count"] == 1
        assert result["matched_sections"] == ["Background"]
        assert result["is_research_rich"] is False

    def test_non_research_sections_ignored(self) -> None:
        """Summary and Acceptance Criteria are not research-indicating."""
        body = """\
## Summary

This is a summary of the feature.

## Acceptance Criteria

- [ ] Feature works
- [ ] Tests pass
"""
        result = detect_issue_research(body)
        assert result["section_count"] == 0
        assert result["matched_sections"] == []
        assert result["is_research_rich"] is False
