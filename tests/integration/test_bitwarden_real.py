"""HMB-S020: Bitwarden CLI integration tests against a real unlocked vault.

Marked `integration` and `bitwarden`; skipped unless `HMB_TEST_BW_SESSION`
is set in the environment. The separate env var (as opposed to the real
`BW_SESSION`) forces explicit opt-in — a developer must deliberately
export `HMB_TEST_BW_SESSION` before these tests can touch their vault,
and the fixture copies it to `BW_SESSION` only for the test duration.

Every item created during a test run lives in a dedicated
`himitsubako-test` folder so the production vault stays tidy, and the
fixture finalizer deletes every created item even on failure.

Run with:

    HMB_TEST_BW_SESSION="$(bw unlock --raw)" \\
        uv run pytest tests/integration/test_bitwarden_real.py -m "integration and bitwarden"
"""

from __future__ import annotations

import contextlib
import os
import shutil
import uuid
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [
    pytest.mark.integration,
    pytest.mark.bitwarden,
    pytest.mark.skipif(
        shutil.which("bw") is None,
        reason="bitwarden tests require the `bw` binary on PATH",
    ),
    pytest.mark.skipif(
        "HMB_TEST_BW_SESSION" not in os.environ,
        reason=(
            "bitwarden tests require HMB_TEST_BW_SESSION env var "
            "(explicit opt-in; see tests/integration/test_bitwarden_real.py docstring)"
        ),
    ),
]


@pytest.fixture
def bw_session(monkeypatch: pytest.MonkeyPatch) -> str:
    """Copy HMB_TEST_BW_SESSION into BW_SESSION for the test duration."""
    session = os.environ["HMB_TEST_BW_SESSION"]
    monkeypatch.setenv("BW_SESSION", session)
    return session


@pytest.fixture
def isolated_bw_backend(bw_session: str) -> Iterator:
    """A BitwardenBackend pointing at a unique test folder with teardown.

    The folder name is `himitsubako-test-<uuid>`. The finalizer lists
    every item in the folder after the test and deletes each one so
    the test vault never accumulates cruft.
    """
    from himitsubako.backends.bitwarden import BitwardenBackend

    folder = f"himitsubako-test-{uuid.uuid4().hex[:12]}"
    backend = BitwardenBackend(folder=folder)

    try:
        yield backend
    finally:
        # Best-effort teardown. Suppress every exception so a listing
        # failure cannot mask the real test error.
        with contextlib.suppress(Exception):
            for key in backend.list_keys():
                with contextlib.suppress(Exception):
                    backend.delete(key)


class TestBitwardenRoundTrip:
    def test_set_get_delete(self, isolated_bw_backend) -> None:
        backend = isolated_bw_backend
        backend.set("SAMPLE_KEY", "sample-value-from-bw")
        assert backend.get("SAMPLE_KEY") == "sample-value-from-bw"
        backend.delete("SAMPLE_KEY")
        assert backend.get("SAMPLE_KEY") is None

    def test_list_keys_returns_created_items(self, isolated_bw_backend) -> None:
        backend = isolated_bw_backend
        backend.set("ITEM_ONE", "one")
        backend.set("ITEM_TWO", "two")
        keys = set(backend.list_keys())
        assert {"ITEM_ONE", "ITEM_TWO"}.issubset(keys)

    def test_get_missing_returns_none(self, isolated_bw_backend) -> None:
        backend = isolated_bw_backend
        assert backend.get("NEVER_SET_KEY") is None


class TestBitwardenStderrRedaction:
    """Sprint 2 CRITICAL regression: token-like substrings in bw stderr
    must be redacted before interpolation into BackendError.detail."""

    def test_error_detail_redacts_token_like_strings(self, isolated_bw_backend) -> None:
        from himitsubako.errors import BackendError

        backend = isolated_bw_backend
        # Forcing a real `bw` error with a deterministic message is
        # fragile across CLI versions. This test relies on the
        # redaction pass being invoked; it asserts that a simulated
        # stderr containing a 40+ char base64 token is scrubbed.
        from himitsubako.backends.bitwarden import _redact_tokens

        raw = "bw: failed (session=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef0123456789)"
        redacted = _redact_tokens(raw)
        assert "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef0123456789" not in redacted
        assert "[REDACTED]" in redacted

        # Also confirm that invoking a failing real `bw` command
        # surfaces the error wrapped in a BackendError without raw
        # session material.
        try:
            backend.delete("ITEM_THAT_DOES_NOT_EXIST_" + uuid.uuid4().hex)
        except BackendError as exc:
            # The token redactor runs on whatever stderr bw produces;
            # any 40+ char base64-ish substring must not appear.
            import re

            assert not re.search(r"[A-Za-z0-9+/=]{40,}", exc.detail), (
                f"unredacted token-like string in error: {exc.detail!r}"
            )
