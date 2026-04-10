"""Error type hierarchy for himitsubako."""

from __future__ import annotations


class HimitsubakoError(Exception):
    """Base exception for all himitsubako errors."""


class BackendError(HimitsubakoError):
    """Error from a specific backend operation."""

    def __init__(self, backend: str, detail: str) -> None:
        self.backend = backend
        self.detail = detail
        super().__init__(f"[{backend}] {detail}")


class ConfigError(HimitsubakoError):
    """Error loading or parsing configuration."""

    def __init__(self, path: str, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"Config error in {path}: {detail}")


class SecretNotFoundError(BackendError):
    """A requested secret key was not found in the backend."""

    def __init__(self, key: str, backend: str = "unknown") -> None:
        self.key = key
        super().__init__(backend, "secret not found")
