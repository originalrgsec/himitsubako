"""Public Python API for himitsubako.

Usage:
    from himitsubako import get, set_secret, list_secrets

    value = get("MY_KEY")
    set_secret("MY_KEY", "new_value")
    keys = list_secrets()
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from himitsubako.backends.sops import SopsBackend

if TYPE_CHECKING:
    from himitsubako.backends.protocol import SecretBackend
from himitsubako.config import find_config, load_config


class _EnvFallbackBackend:
    """Minimal env-var backend used as fallback when no config file exists."""

    @property
    def backend_name(self) -> str:
        return "env"

    def get(self, key: str) -> str | None:
        return os.environ.get(key)

    def set(self, key: str, value: str) -> None:
        msg = (
            "env fallback backend is read-only; "
            "create a .himitsubako.yaml to use a writable backend"
        )
        raise RuntimeError(msg)

    def delete(self, key: str) -> None:
        msg = "env fallback backend is read-only"
        raise RuntimeError(msg)

    def list_keys(self) -> list[str]:
        return list(os.environ.keys())


def _resolve_backend(cwd: Path | None = None) -> SecretBackend:
    """Resolve the appropriate backend based on config files.

    Resolution order:
    1. Walk up from cwd looking for .himitsubako.yaml
    2. If found, use the configured default_backend
    3. If not found but .sops.yaml exists in cwd, use sops backend with defaults
    4. Fall back to env backend (read-only)
    """
    working_dir = cwd or Path.cwd()

    config_path = find_config(working_dir)
    if config_path is not None:
        config = load_config(config_path)
        project_dir = config_path.parent

        if config.default_backend == "sops":
            return SopsBackend(secrets_file=str(project_dir / config.sops.secrets_file))

    # Check for .sops.yaml without .himitsubako.yaml
    sops_yaml = working_dir / ".sops.yaml"
    if sops_yaml.exists():
        return SopsBackend(secrets_file=str(working_dir / ".secrets.enc.yaml"))

    # Fallback to env
    return _EnvFallbackBackend()


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
    The env fallback backend is read-only.
    """
    backend = _resolve_backend()
    backend.set(key, value)


def list_secrets() -> list[str]:
    """List all secret key names from the resolved backend."""
    backend = _resolve_backend()
    return backend.list_keys()
