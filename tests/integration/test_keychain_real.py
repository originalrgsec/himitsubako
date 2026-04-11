"""HMB-S020: macOS Keychain integration tests against the real login keychain.

Marked `integration` and `macos`; skipped on non-Darwin. Every test uses
a uniquely-prefixed service name (`himitsubako-test-<uuid>`) so it cannot
collide with a real user keychain entry, and the fixture's finalizer
deletes every key it created even if the test body raises.

Run with:

    uv run pytest tests/integration/test_keychain_real.py -m "integration and macos"
"""

from __future__ import annotations

import contextlib
import sys
import uuid
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [
    pytest.mark.integration,
    pytest.mark.macos,
    pytest.mark.skipif(
        sys.platform != "darwin",
        reason="keychain integration tests require macOS",
    ),
]


@pytest.fixture
def isolated_keychain_backend() -> Iterator:
    """A KeychainBackend with a unique service name and a full teardown.

    The finalizer walks a list of every key the test stored and calls
    `delete_password` on each, swallowing `PasswordDeleteError` so a
    partial failure during the test still results in full cleanup.
    """
    pytest.importorskip(
        "keyring",
        reason="keychain tests need the [keychain] extra installed",
    )
    from himitsubako.backends.keychain import KeychainBackend

    service = f"himitsubako-test-{uuid.uuid4().hex[:12]}"
    backend = KeychainBackend(service=service)
    created: list[str] = []

    original_set = backend.set

    def tracking_set(key: str, value: str) -> None:
        original_set(key, value)
        if key not in created:
            created.append(key)

    backend.set = tracking_set  # type: ignore[method-assign]

    try:
        yield backend
    finally:
        # Best-effort teardown: delete every key we recorded, tolerating
        # whatever PasswordDeleteError shape the keyring plugin exposes.
        try:
            import keyring
        except ImportError:
            return
        for key in created:
            # Already gone, or the keyring plugin is in a weird state.
            # Either way, there is nothing useful we can do during
            # teardown except not mask the original test failure.
            with contextlib.suppress(Exception):
                keyring.delete_password(service, key)


class TestKeychainRoundTrip:
    def test_set_get_delete_round_trip(self, isolated_keychain_backend) -> None:
        backend = isolated_keychain_backend
        backend.set("SAMPLE_KEY", "sample-value-abc-123")
        assert backend.get("SAMPLE_KEY") == "sample-value-abc-123"

        backend.delete("SAMPLE_KEY")
        assert backend.get("SAMPLE_KEY") is None

    def test_multiple_keys_coexist(self, isolated_keychain_backend) -> None:
        backend = isolated_keychain_backend
        payload = {
            "ALPHA": "alpha-val",
            "BETA": "beta-val",
            "GAMMA": "gamma-val",
        }
        for k, v in payload.items():
            backend.set(k, v)
        for k, v in payload.items():
            assert backend.get(k) == v

    def test_delete_missing_raises_not_found(self, isolated_keychain_backend) -> None:
        from himitsubako.errors import SecretNotFoundError

        backend = isolated_keychain_backend
        with pytest.raises(SecretNotFoundError):
            backend.delete("NEVER_SET_KEY")

    def test_get_missing_returns_none(self, isolated_keychain_backend) -> None:
        backend = isolated_keychain_backend
        assert backend.get("NEVER_SET_KEY") is None


class TestKeychainListKeysUnsupported:
    """list_keys must raise — keyring exposes no enumeration API."""

    def test_list_keys_raises_backend_error(self, isolated_keychain_backend) -> None:
        from himitsubako.errors import BackendError

        backend = isolated_keychain_backend
        with pytest.raises(BackendError, match="list_keys not supported"):
            backend.list_keys()


class TestKeychainAvailability:
    """check_availability is the HMB-S019 ping used by `hmb status`."""

    def test_check_availability_passes_on_macos_login_keychain(
        self, isolated_keychain_backend
    ) -> None:
        # On macOS the default keyring is `macOS.Keyring`, which is not
        # in the deny-list MRO, so check_availability should return None.
        isolated_keychain_backend.check_availability()
