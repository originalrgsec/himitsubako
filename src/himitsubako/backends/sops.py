"""SOPS + age backend — the primary credential backend for himitsubako."""

from __future__ import annotations

import contextlib
import os
import subprocess
import tempfile
from pathlib import Path

import yaml

from himitsubako.errors import BackendError, SecretNotFoundError

_SOPS_TIMEOUT_SECONDS = 30
_SECRETS_FILE_MODE = 0o600
_ENV_SOPS_BIN = "HIMITSUBAKO_SOPS_BIN"


class SopsBackend:
    """Backend that stores secrets in SOPS-encrypted YAML files using age encryption.

    Secrets are stored as key-value pairs in a YAML file encrypted with SOPS.
    Only values are encrypted; keys remain plaintext for readable git diffs.
    """

    def __init__(
        self,
        secrets_file: str,
        sops_bin: str | None = None,
        age_identity: str | None = None,
        sops_config_file: str | None = None,
    ) -> None:
        # Expand `~` eagerly and uniformly across all path inputs so callers see
        # resolved paths when they inspect the backend, and so we don't re-expand
        # on every subprocess call. Applies to secrets_file too: a user writing
        # `secrets_file: ~/vault/secrets.enc.yaml` in .himitsubako.yaml gets the
        # expected path rather than a literal `~`.
        self._secrets_file = os.path.expanduser(secrets_file)
        self._sops_bin_arg = sops_bin
        self._age_identity = os.path.expanduser(age_identity) if age_identity else None
        self._sops_config_file = os.path.expanduser(sops_config_file) if sops_config_file else None

    def _resolve_sops_bin(self) -> str:
        """Resolve the sops binary path: env var > constructor arg > 'sops' on PATH."""
        env_value = os.environ.get(_ENV_SOPS_BIN, "").strip()
        if env_value:
            return env_value
        if self._sops_bin_arg:
            return self._sops_bin_arg
        return "sops"

    def _subprocess_env(self) -> dict[str, str] | None:
        """Build the subprocess env dict, injecting SOPS_AGE_KEY_FILE if configured.

        Returns None when no overrides are needed so the subprocess inherits
        the parent environment directly (identical to pre-S031 behavior).
        """
        if self._age_identity is None:
            return None
        env = dict(os.environ)
        env["SOPS_AGE_KEY_FILE"] = self._age_identity
        return env

    def _config_args(self) -> list[str]:
        """Return the `--config <path>` argv fragment, or [] if not configured.

        Placed immediately after the sops binary name and before the operation
        verb (`--decrypt` / `--encrypt`) in argv. SOPS accepts flags in any
        order; keeping global flags first makes future argv extensions easier
        to reason about.
        """
        if self._sops_config_file is None:
            return []
        return ["--config", self._sops_config_file]

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
        sops_bin = self._resolve_sops_bin()
        argv = [sops_bin, *self._config_args(), "--decrypt", self._secrets_file]
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                check=False,
                timeout=_SOPS_TIMEOUT_SECONDS,
                env=self._subprocess_env(),
            )
        except FileNotFoundError as exc:
            raise BackendError(
                "sops",
                f"sops binary not found at '{sops_bin}'. Install: https://github.com/getsops/sops",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise BackendError(
                "sops",
                f"sops decrypt timed out after {_SOPS_TIMEOUT_SECONDS}s",
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
        sops_bin = self._resolve_sops_bin()

        # Create temp file with 0600 mode from the start so plaintext is never
        # readable by other users on the system, even briefly.
        fd, tmp_name = tempfile.mkstemp(suffix=".yaml", dir=str(parent))
        tmp_path = Path(tmp_name)
        try:
            os.fchmod(fd, _SECRETS_FILE_MODE)
            try:
                tmp_file = os.fdopen(fd, "w")
            except Exception:
                # fdopen failed: close the bare fd ourselves before unlinking,
                # otherwise it leaks for the lifetime of the process.
                os.close(fd)
                raise
            with tmp_file:
                yaml.dump(data, tmp_file, default_flow_style=False)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

        try:
            # --filename-override tells sops to apply creation_rules from
            # .sops.yaml against the real target filename, not the tempfile
            # name generated by mkstemp. Without this, sops emits
            # "no matching creation rules found" because the tempfile
            # name (tmpXXXX.yaml) does not match the shipped default
            # regex (\.secrets\.enc\.yaml$). Discovered by HMB-S013
            # integration tests; latent in v0.1.0 through v0.2.0.
            result = subprocess.run(
                [
                    sops_bin,
                    *self._config_args(),
                    "--encrypt",
                    "--filename-override",
                    str(secrets_path),
                    "--in-place",
                    str(tmp_path),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=_SOPS_TIMEOUT_SECONDS,
                env=self._subprocess_env(),
            )
        except FileNotFoundError as exc:
            tmp_path.unlink(missing_ok=True)
            raise BackendError(
                "sops",
                f"sops binary not found at '{sops_bin}'. Install: https://github.com/getsops/sops",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            tmp_path.unlink(missing_ok=True)
            raise BackendError(
                "sops",
                f"sops encrypt timed out after {_SOPS_TIMEOUT_SECONDS}s",
            ) from exc

        if result.returncode != 0:
            tmp_path.unlink(missing_ok=True)
            raise BackendError("sops", f"failed to encrypt: {result.stderr}")

        # Atomic replace, then re-assert 0600 in case sops or the OS reset it.
        # There is a brief window between rename() and chmod() where the file
        # may carry sops's chosen permissions. This is unavoidable in POSIX
        # without renameat2(RENAME_EXCHANGE), which Python's stdlib does not
        # expose. The window is nanoseconds and the file content is ciphertext.
        tmp_path.replace(secrets_path)
        # No-op on platforms where chmod is unsupported (e.g., Windows).
        with contextlib.suppress(OSError):
            os.chmod(secrets_path, _SECRETS_FILE_MODE)
