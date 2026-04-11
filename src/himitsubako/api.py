"""Public Python API for himitsubako.

Usage:
    from himitsubako import get, set_secret, list_secrets

    value = get("MY_KEY")
    set_secret("MY_KEY", "new_value")
    keys = list_secrets()
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from himitsubako.backends.sops import SopsBackend
from himitsubako.config import HimitsubakoConfig, find_config, load_config
from himitsubako.router import BackendRouter

if TYPE_CHECKING:
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
