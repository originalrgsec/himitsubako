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
`list_keys()` (e.g., the keychain backend) are caught, emitted via
`warnings.warn` as a `UserWarning` so consumers can suppress or capture
the warning with the stdlib `warnings` machinery, and skipped — the
operation does not fail.

Composite backends (HMB-S030 `google-oauth`) are built per-credential rather
than per-backend-name, because each composite entry wraps its own underlying
storage backend with its own key map. The cache is keyed on the route
dictionary key in that case.
"""

from __future__ import annotations

import fnmatch
import warnings
from typing import TYPE_CHECKING

from himitsubako.backends.env import EnvBackend
from himitsubako.backends.sops import SopsBackend
from himitsubako.errors import BackendError

if TYPE_CHECKING:
    from pathlib import Path

    from himitsubako.backends.protocol import SecretBackend
    from himitsubako.config import CredentialRoute, HimitsubakoConfig

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

    def credential_type(self, key: str) -> str | None:
        """Return the backend type declared in the config for an exact-match key.

        Returns the route's `backend` field (e.g. "sops", "google-oauth") if
        `key` has an exact credential entry in config, or None if it does not.
        Glob patterns and default-backend fallbacks are intentionally not
        considered — this is for composite-credential discovery where the
        caller needs to know whether a specific key name is a known
        composite credential before resolving.
        """
        route = self._config.credentials.get(key)
        return route.backend if route is not None else None

    def resolve(self, key: str) -> SecretBackend:
        """Return the backend instance that should handle this key."""
        credentials = self._config.credentials

        # 1. Exact match — composite backends route per-credential.
        if key in credentials:
            route = credentials[key]
            if route.backend == "google-oauth":
                return self._get_composite_backend(key, route)
            return self._get_backend(route.backend)

        # 2. First matching glob (declaration order). Composite backends are
        # not eligible for glob routing — their config is per-credential and
        # the group semantics don't make sense over a pattern.
        for pattern, route in credentials.items():
            if route.backend == "google-oauth":
                continue
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
        composite_credentials: list[tuple[str, CredentialRoute]] = []
        for key, route in self._config.credentials.items():
            if route.backend == "google-oauth":
                composite_credentials.append((key, route))
                # Ensure the underlying storage backend is listed.
                if route.storage_backend is not None:
                    backend_names.add(route.storage_backend)
            else:
                backend_names.add(route.backend)

        for name in backend_names:
            backend = self._get_backend(name)
            try:
                for key in backend.list_keys():
                    seen.add(key)
            except BackendError as exc:
                # HMB-S041 LOW-4: use warnings.warn so library consumers
                # can suppress or capture via stdlib `warnings` channels.
                # Previously this wrote directly to sys.stderr, which
                # library embedders had no clean way to silence.
                warnings.warn(
                    f"backend '{name}' skipped during list: {exc.detail}",
                    stacklevel=2,
                )

        # Composite credentials contribute their logical name on top of the
        # underlying storage keys.
        for credential_name, _route in composite_credentials:
            seen.add(credential_name)

        return sorted(seen)

    def _get_backend(self, name: str) -> SecretBackend:
        """Build (and cache) a backend instance by name."""
        if name in self._cache:
            return self._cache[name]
        backend = self._build_backend(name)
        self._cache[name] = backend
        return backend

    def _get_composite_backend(self, credential_name: str, route: CredentialRoute) -> SecretBackend:
        """Build (and cache) a composite backend keyed on the credential name.

        Composite backends cannot share a single-instance-per-name cache with
        storage backends because two google-oauth credentials can wrap the
        same storage backend but different key maps and scopes.
        """
        cache_key = f"__composite__:{credential_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if route.backend == "google-oauth":
            from himitsubako.backends.google_oauth import GoogleOAuthBackend

            # These fields are required by the config validator for google-oauth
            # routes, but check explicitly so the router is safe to call with a
            # hand-constructed CredentialRoute in tests or third-party code.
            if route.storage_backend is None or route.keys is None or route.scopes is None:
                raise BackendError(
                    "router",
                    f"google-oauth credential '{credential_name}' is missing "
                    "storage_backend, keys, or scopes",
                )
            storage = self._get_backend(route.storage_backend)
            backend: SecretBackend = GoogleOAuthBackend(
                storage=storage,
                credential_name=credential_name,
                keys=route.keys,
                scopes=route.scopes,
            )
        else:  # pragma: no cover — only google-oauth is composite today
            raise BackendError("router", f"unknown composite backend '{route.backend}'")

        self._cache[cache_key] = backend
        return backend

    def _build_backend(self, name: str) -> SecretBackend:
        """Construct a backend from config — extend here when adding backends."""
        if name == "sops":
            sops_cfg = self._config.sops
            return SopsBackend(
                secrets_file=str(self._project_dir / sops_cfg.secrets_file),
                sops_bin=sops_cfg.bin,
                age_identity=sops_cfg.age_identity,
                sops_config_file=sops_cfg.config_file,
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
