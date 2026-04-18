"""Shared redaction helpers for error strings and audit log entries.

The token-shaped-substring redaction was introduced in HMB-S009 (Bitwarden
CLI backend, Sprint 2 review) to prevent `BW_SESSION` tokens from leaking
through `bw` stderr into BackendError.detail. HMB-S021 (audit log, Sprint 4)
reuses the exact same redaction on error strings written to the audit log,
so the helper was lifted out of `backends/bitwarden.py` into this module.

Three patterns run in sequence:

1. **Generic base64-ish opaque tokens** (40+ chars from the base64 alphabet) —
   matches BW session tokens, JWTs, generic API keys.
2. **Google OAuth refresh tokens** — start with `1//` (RFC 6749 opaque string
   shape that Google uses). The `//` would split a generic match because `/`
   is in the base64 class but the leading short prefix is not long enough.
3. **Age private keys** — Bech32 encoding `AGE-SECRET-KEY-1<74 chars>`. The
   embedded hyphens break a generic alphanumeric match.

Added in HMB-S034 (Sprint 8 `/code-review`) per security-reviewer finding
SEC-MED-2.
"""

from __future__ import annotations

import re

_TOKEN_LIKE = re.compile(r"[A-Za-z0-9+/=]{40,}")
_GOOGLE_REFRESH = re.compile(r"1//[A-Za-z0-9_\-]{30,}")
_AGE_SECRET_KEY = re.compile(r"AGE-SECRET-KEY-1[A-Z0-9]{50,}")


def redact_tokens(text: str) -> str:
    """Replace token-like substrings with `[REDACTED]`.

    Three passes: generic opaque tokens, Google OAuth refresh tokens, and
    age private keys. Order matters only for overlapping matches; the
    patterns are disjoint in practice.
    """
    if not text:
        return ""
    text = _AGE_SECRET_KEY.sub("[REDACTED]", text)
    text = _GOOGLE_REFRESH.sub("[REDACTED]", text)
    text = _TOKEN_LIKE.sub("[REDACTED]", text)
    return text
