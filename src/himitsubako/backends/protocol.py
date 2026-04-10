"""SecretBackend protocol — the contract all backends implement."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretBackend(Protocol):
    """Structural protocol for credential backends.

    Any class implementing get, set, delete, list_keys, and backend_name
    is recognized as a SecretBackend without inheriting from this class.
    """

    def get(self, key: str) -> str | None:
        """Return the decrypted value for key, or None if not found."""
        ...

    def set(self, key: str, value: str) -> None:
        """Store a credential under the given key."""
        ...

    def delete(self, key: str) -> None:
        """Remove the credential for the given key."""
        ...

    def list_keys(self) -> list[str]:
        """Return all key names managed by this backend."""
        ...

    @property
    def backend_name(self) -> str:
        """Return the backend identifier (e.g. 'sops', 'env', 'keychain')."""
        ...
