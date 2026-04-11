"""Tests for the Bitwarden CLI backend (HMB-S009)."""

from __future__ import annotations

import contextlib
import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from himitsubako.backends.protocol import SecretBackend


class TestBitwardenBackendProtocol:
    def test_conforms_to_protocol(self):
        from himitsubako.backends.bitwarden import BitwardenBackend

        backend = BitwardenBackend(folder="myproject")
        assert isinstance(backend, SecretBackend)

    def test_backend_name(self):
        from himitsubako.backends.bitwarden import BitwardenBackend

        assert BitwardenBackend(folder="myproject").backend_name == "bitwarden"


class TestBitwardenBackendStrictMode:
    """Default unlock UX: BW_SESSION must be present and non-empty."""

    def test_get_without_bw_session_raises(self, monkeypatch):
        from himitsubako.backends.bitwarden import BitwardenBackend
        from himitsubako.errors import BackendError

        monkeypatch.delenv("BW_SESSION", raising=False)
        backend = BitwardenBackend(folder="myproject")
        with pytest.raises(BackendError, match=r"BW_SESSION not set"):
            backend.get("ANY")

    def test_get_with_empty_bw_session_raises(self, monkeypatch):
        from himitsubako.backends.bitwarden import BitwardenBackend
        from himitsubako.errors import BackendError

        monkeypatch.setenv("BW_SESSION", "")
        backend = BitwardenBackend(folder="myproject")
        with pytest.raises(BackendError, match=r"BW_SESSION"):
            backend.get("ANY")

    def test_set_without_bw_session_raises(self, monkeypatch):
        from himitsubako.backends.bitwarden import BitwardenBackend
        from himitsubako.errors import BackendError

        monkeypatch.delenv("BW_SESSION", raising=False)
        backend = BitwardenBackend(folder="myproject")
        with pytest.raises(BackendError, match=r"BW_SESSION"):
            backend.set("KEY", "value")


class TestBitwardenBackendGet:
    def test_get_returns_value(self, monkeypatch):
        from himitsubako.backends.bitwarden import BitwardenBackend

        monkeypatch.setenv("BW_SESSION", "fake_session_token")
        backend = BitwardenBackend(folder="myproject")

        item_json = json.dumps({"name": "MY_KEY", "notes": "secret_value"})
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=item_json, stderr="")
            result = backend.get("MY_KEY")

        assert result == "secret_value"
        called_argv = mock_run.call_args.args[0]
        assert called_argv[0] == "bw"
        assert "get" in called_argv

    def test_get_missing_returns_none(self, monkeypatch):
        from himitsubako.backends.bitwarden import BitwardenBackend

        monkeypatch.setenv("BW_SESSION", "tok")
        backend = BitwardenBackend(folder="myproject")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Not found.")
            assert backend.get("DOES_NOT_EXIST") is None

    def test_get_locked_vault_raises(self, monkeypatch):
        from himitsubako.backends.bitwarden import BitwardenBackend
        from himitsubako.errors import BackendError

        monkeypatch.setenv("BW_SESSION", "tok")
        backend = BitwardenBackend(folder="myproject")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Vault is locked.")
            with pytest.raises(BackendError, match=r"locked"):
                backend.get("ANY")

    def test_get_timeout_raises(self, monkeypatch):
        from himitsubako.backends.bitwarden import BitwardenBackend
        from himitsubako.errors import BackendError

        monkeypatch.setenv("BW_SESSION", "tok")
        backend = BitwardenBackend(folder="myproject")

        with (
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=["bw"], timeout=30),
            ),
            pytest.raises(BackendError, match=r"timed out"),
        ):
            backend.get("ANY")


class TestBitwardenBackendBinResolution:
    """T-005: pinned bin and HIMITSUBAKO_BW_BIN env override."""

    def test_default_bin_is_bw(self, monkeypatch):
        from himitsubako.backends.bitwarden import BitwardenBackend

        monkeypatch.setenv("BW_SESSION", "tok")
        monkeypatch.delenv("HIMITSUBAKO_BW_BIN", raising=False)
        backend = BitwardenBackend(folder="myproject")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=json.dumps({"notes": "v"}), stderr=""
            )
            backend.get("ANY")

        assert mock_run.call_args.args[0][0] == "bw"

    def test_constructor_bin_override(self, monkeypatch):
        from himitsubako.backends.bitwarden import BitwardenBackend

        monkeypatch.setenv("BW_SESSION", "tok")
        monkeypatch.delenv("HIMITSUBAKO_BW_BIN", raising=False)
        backend = BitwardenBackend(folder="myproject", bin="/opt/custom/bw")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=json.dumps({"notes": "v"}), stderr=""
            )
            backend.get("ANY")

        assert mock_run.call_args.args[0][0] == "/opt/custom/bw"

    def test_env_var_overrides_constructor(self, monkeypatch):
        from himitsubako.backends.bitwarden import BitwardenBackend

        monkeypatch.setenv("BW_SESSION", "tok")
        monkeypatch.setenv("HIMITSUBAKO_BW_BIN", "/from/env/bw")
        backend = BitwardenBackend(folder="myproject", bin="/from/ctor/bw")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=json.dumps({"notes": "v"}), stderr=""
            )
            backend.get("ANY")

        assert mock_run.call_args.args[0][0] == "/from/env/bw"


class TestBitwardenBackendSecrecyHygiene:
    """T-007: BW_SESSION value never appears in errors or output."""

    def test_bw_session_not_in_error_messages(self, monkeypatch):
        from himitsubako.backends.bitwarden import BitwardenBackend
        from himitsubako.errors import BackendError

        monkeypatch.setenv("BW_SESSION", "supersecret_session_xyz")
        backend = BitwardenBackend(folder="myproject")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Vault is locked.")
            try:
                backend.get("ANY")
            except BackendError as exc:
                assert "supersecret_session_xyz" not in str(exc)
                assert "supersecret_session_xyz" not in repr(exc)

    def test_token_like_string_in_stderr_is_redacted(self, monkeypatch):
        """A bw stderr that echoes a base64 token should NOT leak through."""
        from himitsubako.backends.bitwarden import BitwardenBackend
        from himitsubako.errors import BackendError

        monkeypatch.setenv("BW_SESSION", "tok")
        backend = BitwardenBackend(folder="myproject")

        # 50-char base64-ish blob — long enough to trigger _TOKEN_LIKE
        leaked_token = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCdEfGhIjKlMn"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr=f"unexpected error session={leaked_token} ended",
            )
            try:
                backend.get("ANY")
            except BackendError as exc:
                assert leaked_token not in str(exc)
                assert "[REDACTED]" in str(exc)

    def test_credential_value_never_in_subprocess_argv(self, monkeypatch):
        """M-003: set() must pass values via stdin, not argv."""
        from himitsubako.backends.bitwarden import BitwardenBackend

        monkeypatch.setenv("BW_SESSION", "tok")
        backend = BitwardenBackend(folder="myproject")

        secret_value = "do_not_leak_into_argv"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with contextlib.suppress(Exception):
                backend.set("KEY", secret_value)

        for call in mock_run.call_args_list:
            argv = call.args[0]
            for token in argv:
                assert secret_value not in str(token), f"credential value leaked into argv: {argv}"


class TestBitwardenBackendUnlockCommand:
    """Decision 5 option c: unlock_command shells out to obtain a session."""

    def test_unlock_command_runs_when_no_session(self, monkeypatch):
        from himitsubako.backends.bitwarden import BitwardenBackend

        monkeypatch.delenv("BW_SESSION", raising=False)
        backend = BitwardenBackend(folder="myproject", unlock_command="echo master_password")

        # First subprocess call: the unlock_command (returns master password)
        # Second: bw unlock --raw (returns session token)
        # Third: bw get item (returns the credential)
        call_log: list[list[str]] = []

        def fake_run(*args, **kwargs):
            argv = args[0] if args else kwargs["args"]
            call_log.append(list(argv) if isinstance(argv, list) else [str(argv)])
            if "echo" in str(argv):
                return MagicMock(returncode=0, stdout="master_password\n", stderr="")
            if "unlock" in argv:
                return MagicMock(returncode=0, stdout="session_token_xyz", stderr="")
            return MagicMock(returncode=0, stdout=json.dumps({"notes": "secret"}), stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            result = backend.get("MY_KEY")

        assert result == "secret"
        # Verify the unlock command actually ran
        assert any("echo" in " ".join(c) for c in call_log)

    def test_env_session_wins_over_unlock_command(self, monkeypatch):
        from himitsubako.backends.bitwarden import BitwardenBackend

        monkeypatch.setenv("BW_SESSION", "preset_session")
        backend = BitwardenBackend(folder="myproject", unlock_command="should_not_run")

        call_log: list[list[str]] = []

        def fake_run(*args, **kwargs):
            argv = args[0] if args else kwargs["args"]
            call_log.append(list(argv) if isinstance(argv, list) else [str(argv)])
            return MagicMock(returncode=0, stdout=json.dumps({"notes": "v"}), stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            backend.get("ANY")

        # No unlock_command call should appear
        assert not any("should_not_run" in " ".join(c) for c in call_log)
