"""Bitwarden CLI backend (HMB-S009).

The backend invokes the `bw` system binary via `subprocess.run`. The bw
CLI is GPL-3.0 and is used here under the External CLI Tool Invocation
exemption in Obsidian/code/allowed-licenses.md — there is no Python pip
dependency on bitwarden-sdk (see COR-S037 retrospective for why).

Three modes are supported:

1. **Strict (default).** `BW_SESSION` must be set in the process
   environment; the backend never prompts. This is the only mode that
   makes sense for library use from a non-interactive process.
2. **Pinned bin** (`bin` argument or `HIMITSUBAKO_BW_BIN` env var):
   bypasses PATH lookup. Mitigates T-005 (PATH hijack of `bw`).
3. **Shell-out unlock** (`unlock_command` argument): when the env var is
   absent, the backend runs the configured shell command, captures
   stdout as the master password, and pipes it to `bw unlock --raw` to
   obtain a session token used in-memory only. The token is never
   written to disk and never logged. T-022 documents the residual risk
   of an unsafe unlock_command.
"""

from __future__ import annotations

import json
import os
import subprocess

from himitsubako._redaction import redact_tokens as _redact_tokens
from himitsubako.errors import BackendError

_BW_TIMEOUT_SECONDS = 30
_ENV_BW_BIN = "HIMITSUBAKO_BW_BIN"


class BitwardenBackend:
    """SecretBackend implementation backed by the Bitwarden CLI."""

    def __init__(
        self,
        folder: str = "himitsubako",
        bin: str | None = None,
        unlock_command: str | None = None,
    ) -> None:
        self._folder = folder
        self._bin_arg = bin
        self._unlock_command = unlock_command
        self._session: str | None = None  # cached session from unlock_command

    @property
    def backend_name(self) -> str:
        return "bitwarden"

    # ---- Public protocol surface ----

    def get(self, key: str) -> str | None:
        session = self._ensure_session()
        result = self._run_bw(
            ["get", "item", key, "--session", session],
            input_data=None,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").lower()
            if "not found" in stderr or "no object" in stderr:
                return None
            self._raise_friendly(result.stderr)
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise BackendError("bitwarden", f"failed to parse bw output: {exc}") from exc
        # We store the credential value in the item's notes field.
        return data.get("notes")

    def set(self, key: str, value: str) -> None:
        session = self._ensure_session()
        item_payload = json.dumps(
            {"name": key, "notes": value, "type": 2, "secureNote": {"type": 0}}
        )
        # Pipe the JSON via stdin so the value never reaches argv (M-003).
        result = self._run_bw(
            ["create", "item", "--session", session],
            input_data=item_payload,
        )
        if result.returncode != 0:
            self._raise_friendly(result.stderr)

    def delete(self, key: str) -> None:
        session = self._ensure_session()
        result = self._run_bw(
            ["delete", "item", key, "--session", session],
            input_data=None,
        )
        if result.returncode != 0:
            self._raise_friendly(result.stderr)

    def list_keys(self) -> list[str]:
        session = self._ensure_session()
        result = self._run_bw(
            ["list", "items", "--folderid", self._folder, "--session", session],
            input_data=None,
        )
        if result.returncode != 0:
            self._raise_friendly(result.stderr)
        try:
            items = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise BackendError("bitwarden", f"failed to parse bw output: {exc}") from exc
        return [item["name"] for item in items if "name" in item]

    # ---- Private helpers ----

    def _resolve_bin(self) -> str:
        env_value = os.environ.get(_ENV_BW_BIN, "").strip()
        if env_value:
            return env_value
        if self._bin_arg:
            return self._bin_arg
        return "bw"

    def _ensure_session(self) -> str:
        """Resolve a usable BW session token from env, unlock_command, or fail."""
        env_session = os.environ.get("BW_SESSION", "").strip()
        if env_session:
            return env_session

        if self._session:
            return self._session

        if self._unlock_command:
            self._session = self._unlock_via_command()
            return self._session

        raise BackendError(
            "bitwarden",
            "BW_SESSION not set; run 'bw unlock' in your shell first and "
            "export BW_SESSION, or configure bitwarden.unlock_command in "
            ".himitsubako.yaml",
        )

    def _unlock_via_command(self) -> str:
        """Run the configured unlock_command and pipe to 'bw unlock --raw'."""
        if not self._unlock_command:
            raise BackendError("bitwarden", "no unlock_command configured")

        try:
            password_proc = subprocess.run(
                self._unlock_command,
                shell=True,
                capture_output=True,
                text=True,
                check=False,
                timeout=_BW_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise BackendError(
                "bitwarden",
                f"unlock_command timed out after {_BW_TIMEOUT_SECONDS}s",
            ) from exc

        if password_proc.returncode != 0:
            raise BackendError("bitwarden", "unlock_command exited non-zero (output suppressed)")

        master_password = password_proc.stdout.strip()
        if not master_password:
            raise BackendError("bitwarden", "unlock_command produced no output")

        unlock_result = self._run_bw(
            ["unlock", "--raw", "--passwordenv", "BW_PASSWORD"],
            input_data=None,
            extra_env={"BW_PASSWORD": master_password},
        )
        if unlock_result.returncode != 0:
            raise BackendError(
                "bitwarden", "bw unlock failed (master password incorrect or vault unreachable)"
            )

        token = unlock_result.stdout.strip()
        if not token:
            raise BackendError("bitwarden", "bw unlock returned empty session token")
        return token

    def _run_bw(
        self,
        args: list[str],
        *,
        input_data: str | None,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        bw_bin = self._resolve_bin()
        argv = [bw_bin, *args]
        # Build a fresh env dict per call so sensitive extra_env keys
        # cannot leak into a subsequent _run_bw invocation.
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        try:
            return subprocess.run(
                argv,
                capture_output=True,
                text=True,
                check=False,
                timeout=_BW_TIMEOUT_SECONDS,
                input=input_data,
                env=env,
            )
        except FileNotFoundError as exc:
            raise BackendError(
                "bitwarden",
                f"bw binary not found at '{bw_bin}'. Install: https://bitwarden.com/help/cli/",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise BackendError(
                "bitwarden",
                f"bw {args[0] if args else ''} timed out after {_BW_TIMEOUT_SECONDS}s",
            ) from exc
        finally:
            # Defense in depth: explicitly drop any sensitive extra_env keys
            # from the local env dict so a future refactor that promotes env
            # to a longer-lived scope cannot accidentally leak them.
            if extra_env:
                for k in extra_env:
                    env.pop(k, None)

    def _raise_friendly(self, stderr: str) -> None:
        """Convert raw bw stderr into a clean BackendError.

        Sanitizes the stderr text before interpolation so any session
        token or master password that bw echoed into its own error
        output cannot leak through BackendError.detail into log
        aggregators or uncaught-exception handlers.
        """
        text = _redact_tokens((stderr or "").strip())
        lower = text.lower()
        if "locked" in lower:
            raise BackendError(
                "bitwarden",
                "vault is locked; run 'bw unlock' and re-export BW_SESSION",
            )
        if "not authenticated" in lower or "not logged in" in lower:
            raise BackendError("bitwarden", "not logged in; run 'bw login' first")
        raise BackendError("bitwarden", f"bw failed: {text}")
