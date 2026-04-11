"""Configuration model for himitsubako."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 — used at runtime in load_config/find_config

import yaml
from pydantic import BaseModel, field_validator

from himitsubako.errors import ConfigError

_VALID_BACKENDS = frozenset({"sops", "env", "keychain", "bitwarden-cli"})

_CONFIG_FILENAME = ".himitsubako.yaml"


class SopsConfig(BaseModel):
    """SOPS backend configuration."""

    model_config = {"frozen": True}

    secrets_file: str = ".secrets.enc.yaml"
    age_identity: str = "~/.config/sops/age/keys.txt"
    bin: str | None = None


class KeychainConfig(BaseModel):
    """Keychain backend configuration."""

    model_config = {"frozen": True}

    service: str = "himitsubako"


class BitwardenConfig(BaseModel):
    """Bitwarden CLI backend configuration."""

    model_config = {"frozen": True}

    folder: str = "himitsubako"


class EnvConfig(BaseModel):
    """Environment variable backend configuration."""

    model_config = {"frozen": True}

    prefix: str = ""


class HimitsubakoConfig(BaseModel):
    """Top-level configuration parsed from .himitsubako.yaml."""

    model_config = {"frozen": True}

    default_backend: str = "sops"
    sops: SopsConfig = SopsConfig()
    keychain: KeychainConfig = KeychainConfig()
    bitwarden: BitwardenConfig = BitwardenConfig()
    env: EnvConfig = EnvConfig()

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
