"""Public Python API for himitsubako.

Usage:
    from himitsubako import get, set_secret, list_secrets

    value = get("MY_KEY")
    set_secret("MY_KEY", "new_value")
    keys = list_secrets()

For Google OAuth credentials (HMB-S030):

    from himitsubako import get_google_credentials
    creds = get_google_credentials("google_drive")
    # creds is a google.oauth2.credentials.Credentials object
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from himitsubako.backends.sops import SopsBackend
from himitsubako.config import HimitsubakoConfig, find_config, load_config
from himitsubako.errors import BackendError
from himitsubako.router import BackendRouter

if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials

    from himitsubako.backends.protocol import SecretBackend


def _resolve_backend(cwd: Path | None = None) -> SecretBackend:
    """Resolve the appropriate backend (or router) based on config files.

    Resolution order:
    1. Walk up from cwd looking for .himitsubako.yaml. If found, return a
       BackendRouter built from the config. The router handles per-credential
       routing transparently and falls back to `default_backend` for any key
       not matched by `credentials:`.
    2. If not found but .sops.yaml exists in cwd, return a SopsBackend with
       default config (legacy v0.1.x behavior).
    3. Fall back to a read-only EnvBackend() with no prefix.
    """
    working_dir = cwd or Path.cwd()

    config_path = find_config(working_dir)
    if config_path is not None:
        config = load_config(config_path)
        return BackendRouter(config, project_dir=config_path.parent)

    # .sops.yaml-only fallback (legacy v0.1.x)
    sops_yaml = working_dir / ".sops.yaml"
    if sops_yaml.exists():
        return SopsBackend(secrets_file=str(working_dir / ".secrets.enc.yaml"))

    # Final fallback: read-only env backend wrapped in a router so the rest of
    # the codebase always works against a uniform router interface.
    return BackendRouter(HimitsubakoConfig(default_backend="env"), project_dir=working_dir)


def get(key: str) -> str | None:
    """Get a secret value by key.

    Resolves the backend from the nearest .himitsubako.yaml config,
    falls back to .sops.yaml defaults, then to environment variables.
    """
    backend = _resolve_backend()
    return backend.get(key)


def set_secret(key: str, value: str) -> None:
    """Set a secret value for a key.

    Requires a writable backend (sops, keychain, or bitwarden-cli).
    The env backend is read-only and raises BackendError on set/delete.

    Raises:
        BackendError: when the resolved backend is read-only or the
            underlying backend rejects the write.
    """
    backend = _resolve_backend()
    backend.set(key, value)


def list_secrets() -> list[str]:
    """List all secret key names from the resolved backend."""
    backend = _resolve_backend()
    return backend.list_keys()


def get_google_credentials(key: str) -> Credentials:
    """Return a live `google.oauth2.credentials.Credentials` for a google-oauth credential.

    The credential must be declared in `.himitsubako.yaml` with
    `backend: google-oauth`. The returned object carries client_id,
    client_secret, refresh_token, and scopes; the access token is None
    on the returned object and will be refreshed automatically by
    google-api-python-client on first use.

    Requires the `google-auth` package. Install via
    `pip install himitsubako[google]`.

    Raises:
        BackendError: if the key is not declared as a google-oauth
            credential, or any constituent secret is missing.
    """
    from himitsubako.backends.google_oauth import GoogleOAuthBackend

    backend = _resolve_backend()
    if not isinstance(backend, BackendRouter):
        raise BackendError(
            "google-oauth",
            f"'{key}' is not a google-oauth credential (no .himitsubako.yaml config found)",
        )
    if backend.credential_type(key) != "google-oauth":
        raise BackendError(
            "google-oauth",
            f"'{key}' is not a google-oauth credential in .himitsubako.yaml",
        )

    resolved = backend.resolve(key)
    if not isinstance(resolved, GoogleOAuthBackend):  # pragma: no cover — router guarantees
        raise BackendError(
            "google-oauth",
            f"internal error: router returned {type(resolved).__name__} for google-oauth key",
        )
    return resolved.get_credentials()
