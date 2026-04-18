"""Google OAuth composite backend (HMB-S030).

Groups the three Google OAuth secrets (client_id, client_secret, refresh_token)
into a single logical credential. The backend delegates storage to an
underlying backend (`sops`, `env`, `keychain`, `bitwarden-cli`) and adds a
convenience method (`get_credentials`) that returns a live
`google.oauth2.credentials.Credentials` object ready for use with
`google-api-python-client`.

The class conforms to the `SecretBackend` protocol:

- `get(key)` returns the three secrets as a JSON blob.
- `set(key, value)` accepts a JSON blob and writes each underlying secret.
- `delete(key)` removes all three underlying secrets.
- `list_keys()` returns the credential name (singleton).

The `get_credentials()` extension method is what most consumers will call;
the JSON-over-strings surface exists so the credential fits the existing
SecretBackend-uniform CLI (`hmb get`, `hmb set`, `hmb delete`, `hmb list`).

The `google-auth` package is an optional dependency. Install via
`pip install himitsubako[google]`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from himitsubako._redaction import redact_tokens
from himitsubako.errors import BackendError

if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials

    from himitsubako.backends.protocol import SecretBackend


REQUIRED_FIELDS: tuple[str, ...] = ("client_id", "client_secret", "refresh_token")
_GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


class GoogleOAuthBackend:
    """Composite backend grouping three Google OAuth secrets as one credential.

    Instances are built per google-oauth credential entry in the project
    config. The `storage` argument is the underlying backend that holds the
    three constituent secrets; this backend reads/writes through it.
    """

    def __init__(
        self,
        storage: SecretBackend,
        credential_name: str,
        keys: dict[str, str],
        scopes: list[str],
    ) -> None:
        missing = [f for f in REQUIRED_FIELDS if f not in keys]
        if missing:
            # Defensive: config validation should have caught this. Kept so the
            # backend is safe to construct directly in tests and third-party code.
            raise BackendError(
                "google-oauth",
                f"keys mapping missing required fields: {', '.join(missing)}",
            )
        self._storage = storage
        self._credential_name = credential_name
        self._keys = dict(keys)
        self._scopes = list(scopes)

    @property
    def backend_name(self) -> str:
        return "google-oauth"

    @property
    def scopes(self) -> list[str]:
        return list(self._scopes)

    def get_field(self, field: str) -> str | None:
        """Read a single constituent secret by canonical field name.

        Unlike `get()`, this does not require all three fields to be
        present; a missing field returns None. Used by the rotation flow
        (HMB-S032) to recover client_id and client_secret when the
        stored refresh_token is missing or corrupt.

        Raises BackendError if `field` is not one of the canonical names.
        """
        if field not in self._keys:
            raise BackendError(
                "google-oauth",
                f"unknown field '{field}'; expected one of {list(REQUIRED_FIELDS)}",
            )
        return self._storage.get(self._keys[field])

    def get(self, key: str) -> str | None:
        """Return the three secrets as a JSON blob, or None if key does not match."""
        if key != self._credential_name:
            return None
        values = self._read_all()
        return json.dumps(values)

    def set(self, key: str, value: str) -> None:
        """Store all three secrets. `value` must be a JSON object with the three fields."""
        if key != self._credential_name:
            raise BackendError(
                "google-oauth",
                f"unknown google-oauth credential '{key}'; expected '{self._credential_name}'",
            )
        try:
            parsed: object = json.loads(value)
        except json.JSONDecodeError as exc:
            # Do not embed the raw exception string — json.JSONDecodeError can
            # surface the offending document (which could be a raw refresh
            # token if the user misuses set()). Echo only the structural
            # message, not the content. Redact as belt-and-suspenders.
            safe_detail = redact_tokens(exc.msg)
            raise BackendError(
                "google-oauth",
                f"value must be JSON with fields {list(REQUIRED_FIELDS)}: {safe_detail}",
            ) from exc

        if not isinstance(parsed, dict):
            raise BackendError(
                "google-oauth",
                "JSON value must be an object with client_id, client_secret, refresh_token",
            )

        missing = [f for f in REQUIRED_FIELDS if f not in parsed]
        if missing:
            raise BackendError(
                "google-oauth",
                f"JSON value missing required fields: {', '.join(missing)}",
            )

        non_string = [f for f in REQUIRED_FIELDS if not isinstance(parsed[f], str)]
        if non_string:
            raise BackendError(
                "google-oauth",
                f"JSON fields must be strings, got non-string for: {', '.join(non_string)}",
            )

        for field in REQUIRED_FIELDS:
            self._storage.set(self._keys[field], parsed[field])

    def delete(self, key: str) -> None:
        """Remove all three underlying secrets.

        Not transactional: if the storage backend raises after deleting one
        or two keys, the composite credential is left in a degraded state.
        Caller should rerun `hmb delete` to clear whatever remains, or
        manually inspect the storage backend. This limitation is inherent
        to delegating to non-transactional backends.
        """
        if key != self._credential_name:
            raise BackendError(
                "google-oauth",
                f"unknown google-oauth credential '{key}'; expected '{self._credential_name}'",
            )
        for field in REQUIRED_FIELDS:
            self._storage.delete(self._keys[field])

    def list_keys(self) -> list[str]:
        return [self._credential_name]

    def get_credentials(self) -> Credentials:
        """Return a `google.oauth2.credentials.Credentials` object.

        Requires the optional `google-auth` dependency. Install via
        `pip install himitsubako[google]`.
        """
        try:
            from google.oauth2.credentials import Credentials as _Credentials
        except ImportError as exc:  # pragma: no cover - import guard
            raise BackendError(
                "google-oauth",
                "google-auth is not installed. Install with: pip install himitsubako[google]",
            ) from exc

        values = self._read_all()
        return _Credentials(
            token=None,  # auto-refreshed on first API call
            refresh_token=values["refresh_token"],
            client_id=values["client_id"],
            client_secret=values["client_secret"],
            token_uri=_GOOGLE_TOKEN_URI,
            scopes=list(self._scopes),
        )

    def _read_all(self) -> dict[str, str]:
        """Fetch the three secrets from the storage backend.

        Raises BackendError listing any missing fields rather than silently
        returning partial data — the fail-closed semantics match what
        google-api-python-client expects (all three must be present to build
        a Credentials object).
        """
        values: dict[str, str] = {}
        missing: list[str] = []
        for field in REQUIRED_FIELDS:
            storage_key = self._keys[field]
            value = self._storage.get(storage_key)
            if value is None:
                missing.append(field)
            else:
                values[field] = value
        if missing:
            raise BackendError(
                "google-oauth",
                f"credential '{self._credential_name}' is missing: {', '.join(missing)}",
            )
        return values
