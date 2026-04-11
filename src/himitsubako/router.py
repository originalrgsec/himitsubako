"""BackendRouter — per-credential routing across multiple backends (HMB-S012).

The router owns backend resolution and instance caching. It implements the
SecretBackend protocol so it can be passed anywhere a single backend is
expected (CLI dispatch, Python API, pydantic-settings source).

Resolution algorithm for `resolve(key)`:

1. Exact match in `config.credentials` wins.
2. First matching glob pattern (declaration order; uses `fnmatch.fnmatchcase`).
3. Fall back to `config.default_backend`.

`list_keys()` aggregates across the default backend and every distinct
backend referenced in the credentials map. Backends that raise on
`list_keys()` (e.g., the keychain backend) are caught, logged to stderr
as a partial-failure warning, and skipped — the operation does not fail.
"""

from __future__ import annotations

import fnmatch
import sys
from typing import TYPE_CHECKING

from himitsubako.backends.env import EnvBackend
from himitsubako.backends.sops import SopsBackend
from himitsubako.errors import BackendError

if TYPE_CHECKING:
    from pathlib import Path

    from himitsubako.backends.protocol import SecretBackend
    from himitsubako.config import HimitsubakoConfig

_GLOB_CHARS = frozenset("*?[")


def _is_glob(pattern: str) -> bool:
    return any(c in pattern for c in _GLOB_CHARS)


class BackendRouter:
    """Dispatcher that routes individual keys to per-credential backends."""

    def __init__(self, config: HimitsubakoConfig, project_dir: Path) -> None:
        self._config = config
        self._project_dir = project_dir
        self._cache: dict[str, SecretBackend] = {}

    @property
    def backend_name(self) -> str:
        return "router"

    def resolve(self, key: str) -> SecretBackend:
        """Return the backend instance that should handle this key."""
        credentials = self._config.credentials

        # 1. Exact match
        if key in credentials:
            return self._get_backend(credentials[key].backend)

        # 2. First matching glob (declaration order)
        for pattern, route in credentials.items():
            if _is_glob(pattern) and fnmatch.fnmatchcase(key, pattern):
                return self._get_backend(route.backend)

        # 3. Default fallback
        return self._get_backend(self._config.default_backend)

    def get(self, key: str) -> str | None:
        return self.resolve(key).get(key)

    def set(self, key: str, value: str) -> None:
        self.resolve(key).set(key, value)

    def delete(self, key: str) -> None:
        self.resolve(key).delete(key)

    def list_keys(self) -> list[str]:
        """Aggregate keys across all backends in use; skip those that raise."""
        seen: set[str] = set()
        backend_names = {self._config.default_backend}
        for route in self._config.credentials.values():
            backend_names.add(route.backend)

        for name in backend_names:
            backend = self._get_backend(name)
            try:
                for key in backend.list_keys():
                    seen.add(key)
            except BackendError as exc:
                print(
                    f"warning: backend '{name}' skipped during list: {exc.detail}",
                    file=sys.stderr,
                )

        return sorted(seen)

    def _get_backend(self, name: str) -> SecretBackend:
        """Build (and cache) a backend instance by name."""
        if name in self._cache:
            return self._cache[name]
        backend = self._build_backend(name)
        self._cache[name] = backend
        return backend

    def _build_backend(self, name: str) -> SecretBackend:
        """Construct a backend from config — extend here when adding backends."""
        if name == "sops":
            sops_cfg = self._config.sops
            return SopsBackend(
                secrets_file=str(self._project_dir / sops_cfg.secrets_file),
                sops_bin=sops_cfg.bin,
            )

        if name == "env":
            return EnvBackend(prefix=self._config.env.prefix)

        if name == "keychain":
            from himitsubako.backends.keychain import KeychainBackend

            return KeychainBackend(service=self._config.keychain.service)

        if name == "bitwarden-cli":
            from himitsubako.backends.bitwarden import BitwardenBackend

            bw_cfg = self._config.bitwarden
            return BitwardenBackend(
                folder=bw_cfg.folder,
                bin=bw_cfg.bin,
                unlock_command=bw_cfg.unlock_command,
            )

        raise BackendError("router", f"unknown backend '{name}' in routing")
