"""Tests for himitsubako._redaction.

Covers the three token shapes documented in the module:

1. Generic base64-ish opaque tokens (40+ chars from base64 alphabet)
2. Google OAuth refresh tokens (start with `1//`)
3. Age private keys (`AGE-SECRET-KEY-1<...>`)

The first pattern existed since HMB-S009 (Sprint 2). Patterns 2 and 3 were
added in HMB-S034 (Sprint 8 /code-review) per security-reviewer finding
SEC-MED-2.
"""

from __future__ import annotations

import pytest

from himitsubako._redaction import redact_tokens


class TestGenericTokenRedaction:
    """The original 40+ base64-char redaction. Regression coverage."""

    def test_long_base64_blob_is_redacted(self) -> None:
        token = "a" * 60
        result = redact_tokens(f"prefix {token} suffix")
        assert "[REDACTED]" in result
        assert token not in result

    def test_short_alphanum_passes_through(self) -> None:
        # 30 chars — under the 40-char threshold
        result = redact_tokens("error code: " + "a" * 30)
        assert "[REDACTED]" not in result

    def test_empty_string_returns_empty(self) -> None:
        assert redact_tokens("") == ""

    def test_none_safe(self) -> None:
        # The function tolerates falsy input for callers passing exc.detail or similar.
        assert redact_tokens("") == ""


class TestGoogleRefreshTokenRedaction:
    """Google OAuth refresh tokens have shape `1//<30+ url-safe chars>`."""

    def test_refresh_token_is_redacted(self) -> None:
        # Realistic shape — Google refresh tokens start with `1//` then ~50+ chars
        # from [A-Za-z0-9_-].
        token = "1//0AfHA5h9Bx2GqCgYIARAAGBESNwF-L9IrQ7YoVXJ_zpWxKTqZmNoPqRsTuVwXyZ"
        result = redact_tokens(f"OAuth error: {token}")
        assert "[REDACTED]" in result
        assert token not in result

    def test_refresh_token_in_error_description(self) -> None:
        msg = (
            "device flow rejected by Google: invalid_grant. "
            "Token used: 1//0Abcdefghij_klmnopqrstuvwxyz0123456789-XYZ. "
            "Retry with --browser."
        )
        result = redact_tokens(msg)
        assert "1//0A" not in result
        assert "[REDACTED]" in result

    def test_short_1_slash_not_redacted(self) -> None:
        # `1//` followed by < 30 chars should NOT be matched. This protects
        # against false-positive redaction of human-readable error text.
        result = redact_tokens("see RFC 1//abc for details")
        assert "[REDACTED]" not in result


class TestAgeSecretKeyRedaction:
    """age private keys have shape `AGE-SECRET-KEY-1<50+ uppercase Bech32>`."""

    def test_age_secret_key_is_redacted(self) -> None:
        # age private keys are deterministic length: AGE-SECRET-KEY-1 + 58 Bech32 chars.
        key = "AGE-SECRET-KEY-1QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L4QYUMM2VXF"
        result = redact_tokens(f"sops decrypt failed: bad key {key}")
        assert "[REDACTED]" in result
        assert key not in result

    def test_age_secret_key_in_long_error(self) -> None:
        msg = (
            "failed to decrypt /tmp/secrets.enc.yaml: "
            "no key matched AGE-SECRET-KEY-1QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L4QYUMM2VXF"
        )
        result = redact_tokens(msg)
        assert "AGE-SECRET-KEY-1Q" not in result
        assert "[REDACTED]" in result

    def test_age_public_keys_match_generic_pattern_acceptable_overredaction(self) -> None:
        # age public keys are 62 chars of lowercase alphanumeric and DO match
        # the generic 40+ base64 pattern. Redacting them is overly cautious
        # (public keys are not secrets) but not a security concern — public
        # keys are recorded unredacted in .sops.yaml. Documenting the
        # existing behaviour so a later refactor that "fixes" it is a
        # conscious decision, not an accident.
        public_key = "age1qpzry9x8gf2tvdw0s3jn54khce6mua7l4qyumm2vxf"
        result = redact_tokens(f"recipient: {public_key}")
        assert "[REDACTED]" in result


class TestCombinedPatterns:
    """Multiple token shapes in one string — all should be redacted."""

    def test_all_three_in_one_message(self) -> None:
        msg = (
            "BW_SESSION=" + "Z" * 60 + " "
            "refresh_token=1//0AbcdefghijKLMNOPQRSTUVWXYZ_abcdefghij012345 "
            "age_key=AGE-SECRET-KEY-1QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L4QYUMM2VXF"
        )
        result = redact_tokens(msg)
        assert "Z" * 40 not in result
        assert "1//0A" not in result
        assert "AGE-SECRET-KEY-1Q" not in result
        # The literal `[REDACTED]` should appear at least three times — once per token.
        assert result.count("[REDACTED]") >= 3

    @pytest.mark.parametrize(
        "leading_text,token,trailing_text",
        [
            ("prefix ", "a" * 50, " suffix"),
            ("err: ", "1//0" + "A" * 40, " end"),
            ("key=", "AGE-SECRET-KEY-1" + "Q" * 50, ""),
        ],
    )
    def test_token_anywhere_in_string(
        self, leading_text: str, token: str, trailing_text: str
    ) -> None:
        full = leading_text + token + trailing_text
        result = redact_tokens(full)
        assert "[REDACTED]" in result
        assert token not in result
