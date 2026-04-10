"""SOPS + age backend — the primary credential backend for himitsubako."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import yaml

from himitsubako.errors import BackendError, SecretNotFoundError


class SopsBackend:
    """Backend that stores secrets in SOPS-encrypted YAML files using age encryption.

    Secrets are stored as key-value pairs in a YAML file encrypted with SOPS.
    Only values are encrypted; keys remain plaintext for readable git diffs.
    """

    def __init__(self, secrets_file: str) -> None:
        self._secrets_file = secrets_file

    @property
    def backend_name(self) -> str:
        return "sops"

    def get(self, key: str) -> str | None:
        """Return the decrypted value for key, or None if not found."""
        data = self._decrypt()
        value = data.get(key)
        if value is None:
            return None
        return str(value)

    def set(self, key: str, value: str) -> None:
        """Store a credential. Decrypts, updates, and re-encrypts the secrets file."""
        data = self._decrypt()
        updated = {**data, key: value}
        self._encrypt(updated)

    def delete(self, key: str) -> None:
        """Remove a credential. Raises SecretNotFoundError if key does not exist."""
        data = self._decrypt()
        if key not in data:
            raise SecretNotFoundError(key, backend="sops")
        updated = {k: v for k, v in data.items() if k != key}
        self._encrypt(updated)

    def list_keys(self) -> list[str]:
        """Return all key names from the encrypted secrets file."""
        data = self._decrypt()
        return list(data.keys())

    def _decrypt(self) -> dict[str, str]:
        """Decrypt the secrets file and return its contents as a dict."""
        try:
            result = subprocess.run(
                ["sops", "--decrypt", self._secrets_file],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise BackendError(
                "sops", "sops binary not found on PATH. Install: https://github.com/getsops/sops"
            ) from exc

        if result.returncode != 0:
            raise BackendError("sops", f"failed to decrypt {self._secrets_file}: {result.stderr}")

        raw = yaml.safe_load(result.stdout)
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            actual_type = type(raw).__name__
            raise BackendError(
                "sops", f"expected YAML mapping in {self._secrets_file}, got {actual_type}"
            )
        return {str(k): str(v) for k, v in raw.items()}

    def _encrypt(self, data: dict[str, str]) -> None:
        """Write data to a temp file, encrypt in place with SOPS, then move to secrets_file."""
        secrets_path = Path(self._secrets_file)
        parent = secrets_path.parent
        parent.mkdir(parents=True, exist_ok=True)

        # Write plaintext to a temp file in the same directory (for atomic rename)
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            dir=str(parent),
            delete=False,
        ) as tmp:
            yaml.dump(data, tmp, default_flow_style=False)
            tmp_path = Path(tmp.name)

        try:
            result = subprocess.run(
                ["sops", "--encrypt", "--in-place", str(tmp_path)],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            tmp_path.unlink(missing_ok=True)
            raise BackendError(
                "sops", "sops binary not found on PATH. Install: https://github.com/getsops/sops"
            ) from exc

        if result.returncode != 0:
            tmp_path.unlink(missing_ok=True)
            raise BackendError("sops", f"failed to encrypt: {result.stderr}")

        # Atomic replace
        tmp_path.replace(secrets_path)
