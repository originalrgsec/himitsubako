"""Configuration model for himitsubako."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 — used at runtime in load_config/find_config

import yaml
from pydantic import BaseModel, field_validator, model_validator

from himitsubako.errors import ConfigError

# Simple storage backends that can also serve as `storage_backend` for composite
# credentials (e.g. google-oauth). `google-oauth` is itself a composite and
# cannot be used as its own storage.
_STORAGE_BACKENDS = frozenset({"sops", "env", "keychain", "bitwarden-cli"})
_VALID_BACKENDS = _STORAGE_BACKENDS | {"google-oauth"}

_GOOGLE_OAUTH_REQUIRED_KEYS = frozenset({"client_id", "client_secret", "refresh_token"})

_CONFIG_FILENAME = ".himitsubako.yaml"


class SopsConfig(BaseModel):
    """SOPS backend configuration.

    `age_identity` and `config_file` are both optional. When unset, SOPS
    performs its own resolution (default key path, cwd-walk for `.sops.yaml`).
    When set, they are propagated to the sops subprocess as
    `SOPS_AGE_KEY_FILE` env var and `--config` flag respectively.
    """

    model_config = {"frozen": True}

    secrets_file: str = ".secrets.enc.yaml"
    age_identity: str | None = None
    config_file: str | None = None
    bin: str | None = None


class KeychainConfig(BaseModel):
    """Keychain backend configuration."""

    model_config = {"frozen": True}

    service: str = "himitsubako"


class BitwardenConfig(BaseModel):
    """Bitwarden CLI backend configuration."""

    model_config = {"frozen": True}

    folder: str = "himitsubako"
    bin: str | None = None
    unlock_command: str | None = None


class EnvConfig(BaseModel):
    """Environment variable backend configuration."""

    model_config = {"frozen": True}

    prefix: str = ""


class CredentialRoute(BaseModel):
    """Per-credential routing override.

    A `credentials:` entry in `.himitsubako.yaml` may name an exact key
    or a glob pattern (`fnmatch` syntax). Each entry must specify a
    `backend` field; routes inherit the project-level backend config
    sections (`sops:`, `keychain:`, etc.) for connection details.

    When `backend` is `google-oauth` (HMB-S030), the route is a composite:
    it groups three underlying secrets (client_id, client_secret, refresh_token)
    into a single logical credential. The `storage_backend`, `scopes`, and
    `keys` fields are required in that case and forbidden otherwise.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    backend: str
    # Composite-only fields, validated below.
    storage_backend: str | None = None
    scopes: list[str] | None = None
    keys: dict[str, str] | None = None

    @field_validator("backend")
    @classmethod
    def _validate_backend(cls, v: str) -> str:
        if v not in _VALID_BACKENDS:
            raise ValueError(
                f"unknown backend '{v}' in credentials route. "
                f"Choose from: {', '.join(sorted(_VALID_BACKENDS))}"
            )
        return v

    @model_validator(mode="after")
    def _validate_composite_fields(self) -> CredentialRoute:
        """Enforce that composite-only fields appear only with composite backends."""
        composite_fields = {
            "storage_backend": self.storage_backend,
            "scopes": self.scopes,
            "keys": self.keys,
        }
        present = [name for name, value in composite_fields.items() if value is not None]

        if self.backend == "google-oauth":
            # Require all three composite fields and specific keys.
            missing = [name for name, value in composite_fields.items() if value is None]
            if missing:
                raise ValueError(
                    f"google-oauth credential missing required fields: {', '.join(missing)}"
                )
            if self.storage_backend not in _STORAGE_BACKENDS:
                raise ValueError(
                    f"storage_backend '{self.storage_backend}' is not a valid storage "
                    f"backend. Choose from: {', '.join(sorted(_STORAGE_BACKENDS))}"
                )
            if self.keys is None:  # pragma: no cover — guarded by missing check
                raise ValueError("google-oauth credential requires keys mapping")
            missing_keys = _GOOGLE_OAUTH_REQUIRED_KEYS - set(self.keys.keys())
            if missing_keys:
                raise ValueError(
                    f"google-oauth credential keys missing: {', '.join(sorted(missing_keys))}"
                )
            extra_keys = set(self.keys.keys()) - _GOOGLE_OAUTH_REQUIRED_KEYS
            if extra_keys:
                raise ValueError(
                    f"google-oauth credential keys has unexpected entries: "
                    f"{', '.join(sorted(extra_keys))}"
                )
        elif present:
            raise ValueError(
                f"fields {present} are only valid when backend is 'google-oauth', "
                f"not '{self.backend}'"
            )
        return self


class HimitsubakoConfig(BaseModel):
    """Top-level configuration parsed from .himitsubako.yaml."""

    model_config = {"frozen": True}

    default_backend: str = "sops"
    sops: SopsConfig = SopsConfig()
    keychain: KeychainConfig = KeychainConfig()
    bitwarden: BitwardenConfig = BitwardenConfig()
    env: EnvConfig = EnvConfig()
    credentials: dict[str, CredentialRoute] = {}

    @field_validator("default_backend")
    @classmethod
    def _validate_backend(cls, v: str) -> str:
        if v not in _VALID_BACKENDS:
            raise ValueError(
                f"unknown backend '{v}': not a valid backend. "
                f"Choose from: {', '.join(sorted(_VALID_BACKENDS))}"
            )
        return v


def load_config(path: Path) -> HimitsubakoConfig:
    """Load and validate a config file from the given path."""
    if not path.exists():
        raise ConfigError(str(path), "file not found")

    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(str(path), f"invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(str(path), "expected a YAML mapping at top level")

    try:
        return HimitsubakoConfig(**raw)
    except (ValueError, TypeError) as exc:
        raise ConfigError(str(path), str(exc)) from exc


def find_config(start: Path, *, stop_at: Path | None = None) -> Path | None:
    """Walk up from start looking for .himitsubako.yaml.

    Returns the path to the config file, or None if not found.
    Stops at stop_at (exclusive) or the filesystem root.
    """
    current = start.resolve()
    stop = stop_at.resolve() if stop_at else None

    while True:
        candidate = current / _CONFIG_FILENAME
        if candidate.is_file():
            return candidate

        parent = current.parent
        if parent == current:
            # Reached filesystem root
            return None
        if stop and current == stop:
            return None

        current = parent
