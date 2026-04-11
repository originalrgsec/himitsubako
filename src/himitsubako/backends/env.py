"""Environment variable backend — first-class read-only backend (HMB-S007).

The env backend is the zero-dependency escape hatch for CI/CD pipelines,
containers, and 12-factor deployments. Values are sourced from os.environ
on every call (no caching). It is also the implicit fallback when no
.himitsubako.yaml or .sops.yaml is found in the working directory tree.

Read-only by design: env vars are set externally (shell export, .envrc,
container runtime) and the backend refuses set/delete to keep the source
of truth outside the library.
"""

from __future__ import annotations

import os

from himitsubako.errors import BackendError

_READ_ONLY_MESSAGE = (
    "env backend is read-only; "
    "export the variable in your shell, .envrc, or container runtime"
)


class EnvBackend:
    """SecretBackend implementation backed by os.environ.

    With prefix=""  (default): get/list operate on the full environment.
    With prefix="X_": get("KEY") resolves "X_KEY" and list_keys() returns
    only matching variables, with the prefix stripped from the returned names.

    WARNING: with an empty prefix, list_keys() returns every environment
    variable in the process — including credentials inherited from the
    shell that have nothing to do with himitsubako. Configure a prefix
    in `.himitsubako.yaml` (`env.prefix: MYAPP_`) for any non-trivial
    use. The CLI emits a warning when hmb list runs against an
    unprefixed env backend.
    """

    def __init__(self, prefix: str = "") -> None:
        self._prefix = prefix

    @property
    def backend_name(self) -> str:
        return "env"

    @property
    def prefix(self) -> str:
        """The configured key prefix; empty string means no filtering."""
        return self._prefix

    def get(self, key: str) -> str | None:
        """Return the env var value for prefix+key, or None if unset."""
        return os.environ.get(self._prefix + key)

    def set(self, key: str, value: str) -> None:
        """Always raises BackendError — env backend is read-only."""
        raise BackendError("env", _READ_ONLY_MESSAGE)

    def delete(self, key: str) -> None:
        """Always raises BackendError — env backend is read-only."""
        raise BackendError("env", _READ_ONLY_MESSAGE)

    def list_keys(self) -> list[str]:
        """Return env var names. With a prefix, filter and strip it."""
        if not self._prefix:
            return list(os.environ.keys())
        plen = len(self._prefix)
        return [
            name[plen:]
            for name in os.environ
            if name.startswith(self._prefix)
        ]
