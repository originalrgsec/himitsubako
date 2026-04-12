"""Shared redaction helpers for error strings and audit log entries.

The token-shaped-substring redaction was introduced in HMB-S009 (Bitwarden
CLI backend, Sprint 2 review) to prevent `BW_SESSION` tokens from leaking
through `bw` stderr into BackendError.detail. HMB-S021 (audit log, Sprint 4)
reuses the exact same redaction on error strings written to the audit log,
so the helper was lifted out of `backends/bitwarden.py` into this module.

Anything 40 or more consecutive characters from the base64 alphabet
([A-Za-z0-9+/=]) is replaced with `[REDACTED]`. This matches the Bitwarden
CLI's session token shape and is also a reasonable heuristic for API keys,
JWTs, and most other long opaque credentials.
"""

from __future__ import annotations

import re

_TOKEN_LIKE = re.compile(r"[A-Za-z0-9+/=]{40,}")


def redact_tokens(text: str) -> str:
    """Replace any token-like substring (40+ base64 chars) with `[REDACTED]`."""
    return _TOKEN_LIKE.sub("[REDACTED]", text or "")
