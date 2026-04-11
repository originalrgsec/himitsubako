"""macOS Keychain backend via the keyring library (HMB-S008).

Delegates credential storage to the OS-native secret store. On macOS this
is the Keychain (`Security.framework`); on Linux it can be `gnome-keyring`,
`kwallet`, or any other keyring backend resolved by `keyring.get_keyring()`.

Three notable design choices:

1. **list_keys() raises.** The `keyring` public API does not expose
   enumeration. Returning an empty list silently misleads callers; an
   explicit error is more honest. Decision 4 in HMB-S008.

2. **Insecure-backend deny-list.** keyring auto-resolves a backend at
   import time. On a misconfigured Linux host this can fall back to
   `Null` or `PlaintextKeyring`, which would silently store secrets in
   the clear or drop them on the floor. The deny-list (M-015 mitigation
   for T-023) refuses to operate when the resolved backend class is in
   the deny-list and points the user at a remediation.

3. **keyring is an optional dependency.** Wrapped behind the `[keychain]`
   pyproject extra. ImportError is converted to a clear BackendError
   pointing at the install command.
"""

from __future__ import annotations

import contextlib

from himitsubako.errors import BackendError, SecretNotFoundError

_INSECURE_BACKEND_NAMES = frozenset(
    {"Null", "PlaintextKeyring", "EncryptedKeyring", "fail.Keyring"}
)


class KeychainBackend:
    """SecretBackend implementation backed by the OS keyring."""

    def __init__(self, service: str = "himitsubako") -> None:
        self._service = service

    @property
    def backend_name(self) -> str:
        return "keychain"

    def get(self, key: str) -> str | None:
        keyring = self._resolve_keyring()
        try:
            value = keyring.get_password(self._service, key)
        except Exception as exc:
            raise BackendError("keychain", f"keyring get failed: {exc}") from exc
        return value

    def set(self, key: str, value: str) -> None:
        keyring = self._resolve_keyring()
        try:
            keyring.set_password(self._service, key, value)
        except Exception as exc:
            raise BackendError("keychain", f"keyring set failed: {exc}") from exc

    def delete(self, key: str) -> None:
        keyring = self._resolve_keyring()
        # PasswordDeleteError is the keyring-specific signal for "no such key".
        delete_err: type[BaseException] = Exception
        with contextlib.suppress(AttributeError):
            delete_err = keyring.errors.PasswordDeleteError

        try:
            keyring.delete_password(self._service, key)
        except delete_err as exc:
            raise SecretNotFoundError(key, backend="keychain") from exc
        except Exception as exc:
            raise BackendError("keychain", f"keyring delete failed: {exc}") from exc

    def list_keys(self) -> list[str]:
        """Always raises — keyring does not expose key enumeration."""
        raise BackendError(
            "keychain",
            "list_keys not supported by macOS Keychain backend; "
            "enumerate keys via your config file or secrets registry",
        )

    def check_availability(self) -> None:
        """Ping-style availability check for `hmb status`.

        Imports keyring, resolves a backend, and walks the deny-list MRO.
        Raises BackendError on any failure; returns None on success. Does
        not read, write, or enumerate any credential.
        """
        self._resolve_keyring()

    def _import_keyring(self):
        """Lazy import wrapper, kept as a method so tests can patch it."""
        try:
            import keyring as keyring_module
            from keyring import errors as _errors
        except ImportError as exc:
            raise BackendError(
                "keychain",
                "keychain backend requires 'keyring'; "
                "install with 'pip install himitsubako[keychain]'",
            ) from exc
        # Attach the errors submodule explicitly so callers can do
        # `keyring.errors.PasswordDeleteError` even if the side-effect
        # registration was bypassed by a stale package state.
        keyring_module.errors = _errors
        return keyring_module

    def _resolve_keyring(self):
        """Import keyring and reject insecure backends.

        The deny-list check walks the resolved keyring's MRO so a
        subclass of `PlaintextKeyring` (or any other denied class)
        cannot bypass the gate by changing only its leaf class name.
        """
        keyring = self._import_keyring()
        resolved = keyring.get_keyring()
        mro_names = {cls.__name__ for cls in type(resolved).__mro__}
        bad = mro_names & _INSECURE_BACKEND_NAMES
        if bad:
            raise BackendError(
                "keychain",
                f"keyring resolved to insecure backend '{type(resolved).__name__}' "
                f"(MRO matches {sorted(bad)}); "
                "install gnome-keyring (Linux), use macOS Keychain (Darwin), "
                "or set keyring's preferred backend explicitly",
            )
        return keyring
