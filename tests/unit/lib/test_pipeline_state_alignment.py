"""
Tests for alignment_passed field in pipeline_state.py HMAC computation (Issue #585).

Validates that:
1. alignment_passed is included in the HMAC-protected message
2. Tampering with alignment_passed invalidates the HMAC
3. Backward compatibility: state without alignment_passed field signs/verifies correctly
4. Full sign/verify roundtrip with alignment_passed=True

Date: 2026-03-28
Issue: #585
"""

import sys
from pathlib import Path

import pytest

# Add lib directory to path
LIB_DIR = Path(__file__).resolve().parents[3] / "plugins" / "autonomous-dev" / "lib"
sys.path.insert(0, str(LIB_DIR))

from pipeline_state import (
    _compute_state_hmac,
    cleanup_pipeline_secret,
    sign_state,
    verify_state_hmac,
)


def _make_state(**overrides) -> dict:
    """Create a base pipeline state dict for testing."""
    state = {
        "session_start": "2026-03-28T10:00:00",
        "mode": "full",
        "run_id": "test-alignment-585",
        "explicitly_invoked": True,
    }
    state.update(overrides)
    return state


SESSION_ID = "session-alignment-585"


class TestHmacIncludesAlignmentPassed:
    """Verify alignment_passed is included in HMAC computation."""

    def test_hmac_includes_alignment_passed(self):
        """Sign with alignment_passed=True, tamper to False, verify fails."""
        state = _make_state(alignment_passed=True)
        signed = sign_state(state, SESSION_ID)
        assert verify_state_hmac(signed, SESSION_ID) is True

        # Tamper: flip alignment_passed without re-signing
        signed["alignment_passed"] = False
        assert verify_state_hmac(signed, SESSION_ID) is False
        cleanup_pipeline_secret("test-alignment-585")

    def test_hmac_tamper_false_to_true_detected(self):
        """Sign with alignment_passed=False, tamper to True, verify fails."""
        state = _make_state(alignment_passed=False)
        signed = sign_state(state, SESSION_ID)
        assert verify_state_hmac(signed, SESSION_ID) is True

        # Tamper: flip to True without re-signing
        signed["alignment_passed"] = True
        assert verify_state_hmac(signed, SESSION_ID) is False
        cleanup_pipeline_secret("test-alignment-585")


class TestHmacBackwardCompatNoAlignmentField:
    """Backward compatibility: state without alignment_passed field."""

    def test_backward_compat_no_alignment_field(self):
        """State without alignment_passed signs/verifies correctly (defaults to False)."""
        state = _make_state(run_id="test-alignment-compat")
        # No alignment_passed key at all
        assert "alignment_passed" not in state
        signed = sign_state(state, SESSION_ID)
        assert verify_state_hmac(signed, SESSION_ID) is True
        cleanup_pipeline_secret("test-alignment-compat")

    def test_compute_hmac_deterministic_without_alignment(self):
        """_compute_state_hmac produces same result when alignment_passed is absent."""
        state = _make_state(nonce="fixed-nonce", run_id="test-compat-det")
        h1 = _compute_state_hmac(state, SESSION_ID)
        h2 = _compute_state_hmac(state, SESSION_ID)
        assert h1 == h2


class TestSignVerifyRoundtripWithAlignment:
    """Full sign/verify cycle with alignment_passed field."""

    def test_roundtrip_alignment_true(self):
        """Full cycle: sign with alignment_passed=True, verify succeeds."""
        state = _make_state(alignment_passed=True, run_id="test-roundtrip-true")
        signed = sign_state(state, SESSION_ID)
        assert "hmac" in signed
        assert "nonce" in signed
        assert signed["alignment_passed"] is True
        assert verify_state_hmac(signed, SESSION_ID) is True
        cleanup_pipeline_secret("test-roundtrip-true")

    def test_roundtrip_alignment_false(self):
        """Full cycle: sign with alignment_passed=False, verify succeeds."""
        state = _make_state(alignment_passed=False, run_id="test-roundtrip-false")
        signed = sign_state(state, SESSION_ID)
        assert signed["alignment_passed"] is False
        assert verify_state_hmac(signed, SESSION_ID) is True
        cleanup_pipeline_secret("test-roundtrip-false")

    def test_different_alignment_values_different_hmac(self):
        """alignment_passed=True vs False produces different HMAC (same nonce)."""
        state_true = _make_state(
            alignment_passed=True, nonce="same-nonce", run_id="test-diff-hmac"
        )
        state_false = _make_state(
            alignment_passed=False, nonce="same-nonce", run_id="test-diff-hmac"
        )
        h_true = _compute_state_hmac(state_true, SESSION_ID)
        h_false = _compute_state_hmac(state_false, SESSION_ID)
        assert h_true != h_false
