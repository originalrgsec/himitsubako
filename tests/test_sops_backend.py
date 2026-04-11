"""Tests for the SOPS+age backend."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from himitsubako.backends.protocol import SecretBackend


class TestSopsBackendProtocol:
    """Verify the SOPS backend conforms to the SecretBackend protocol."""

    def test_conforms_to_protocol(self):
        from himitsubako.backends.sops import SopsBackend

        backend = SopsBackend(secrets_file="/tmp/fake.enc.yaml")
        assert isinstance(backend, SecretBackend)

    def test_backend_name(self):
        from himitsubako.backends.sops import SopsBackend

        backend = SopsBackend(secrets_file="/tmp/fake.enc.yaml")
        assert backend.backend_name == "sops"


class TestSopsBackendGet:
    """Test get() with mocked subprocess calls."""

    def test_get_existing_key(self):
        from himitsubako.backends.sops import SopsBackend

        decrypted = yaml.dump({"MY_KEY": "secret_value"})
        backend = SopsBackend(secrets_file="/tmp/fake.enc.yaml")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=decrypted, stderr=""
            )
            result = backend.get("MY_KEY")

        assert result == "secret_value"

    def test_get_missing_key_returns_none(self):
        from himitsubako.backends.sops import SopsBackend

        decrypted = yaml.dump({"OTHER_KEY": "other_value"})
        backend = SopsBackend(secrets_file="/tmp/fake.enc.yaml")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=decrypted, stderr=""
            )
            result = backend.get("NONEXISTENT")

        assert result is None

    def test_get_sops_binary_missing_raises(self):
        from himitsubako.backends.sops import SopsBackend
        from himitsubako.errors import BackendError

        backend = SopsBackend(secrets_file="/tmp/fake.enc.yaml")

        with (
            patch("subprocess.run", side_effect=FileNotFoundError("sops")),
            pytest.raises(BackendError, match=r"sops.*not found"),
        ):
            backend.get("MY_KEY")

    def test_get_decryption_failure_raises(self):
        from himitsubako.backends.sops import SopsBackend
        from himitsubako.errors import BackendError

        backend = SopsBackend(secrets_file="/tmp/fake.enc.yaml")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128, stdout="", stderr="Error decrypting key"
            )
            with pytest.raises(BackendError, match="decrypt"):
                backend.get("MY_KEY")


class TestSopsBackendSet:
    """Test set() with mocked subprocess calls."""

    def test_set_new_key(self, tmp_path):
        from himitsubako.backends.sops import SopsBackend

        secrets_file = tmp_path / ".secrets.enc.yaml"
        backend = SopsBackend(secrets_file=str(secrets_file))

        # First call: decrypt existing (empty or new file)
        # Second call: encrypt updated content
        decrypted_empty = yaml.dump({})

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                # decrypt call
                MagicMock(returncode=0, stdout=decrypted_empty, stderr=""),
                # encrypt call
                MagicMock(returncode=0, stdout="", stderr=""),
            ]
            backend.set("NEW_KEY", "new_value")

        # Verify encrypt was called
        assert mock_run.call_count == 2

    def test_set_sops_binary_missing_raises(self):
        from himitsubako.backends.sops import SopsBackend
        from himitsubako.errors import BackendError

        backend = SopsBackend(secrets_file="/tmp/fake.enc.yaml")

        with (
            patch("subprocess.run", side_effect=FileNotFoundError("sops")),
            pytest.raises(BackendError, match=r"sops.*not found"),
        ):
            backend.set("KEY", "value")


class TestSopsBackendDelete:
    """Test delete() with mocked subprocess calls."""

    def test_delete_existing_key(self, tmp_path):
        from himitsubako.backends.sops import SopsBackend

        secrets_file = tmp_path / ".secrets.enc.yaml"
        backend = SopsBackend(secrets_file=str(secrets_file))

        decrypted = yaml.dump({"KEY_A": "val_a", "KEY_B": "val_b"})

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                # decrypt
                MagicMock(returncode=0, stdout=decrypted, stderr=""),
                # encrypt
                MagicMock(returncode=0, stdout="", stderr=""),
            ]
            backend.delete("KEY_A")

        assert mock_run.call_count == 2

    def test_delete_missing_key_raises(self):
        from himitsubako.backends.sops import SopsBackend
        from himitsubako.errors import SecretNotFoundError

        backend = SopsBackend(secrets_file="/tmp/fake.enc.yaml")

        decrypted = yaml.dump({"OTHER": "val"})

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=decrypted, stderr=""
            )
            with pytest.raises(SecretNotFoundError):
                backend.delete("NONEXISTENT")


class TestSopsBackendListKeys:
    """Test list_keys() with mocked subprocess calls."""

    def test_list_keys_returns_all_names(self):
        from himitsubako.backends.sops import SopsBackend

        decrypted = yaml.dump({"KEY_A": "val_a", "KEY_B": "val_b", "KEY_C": "val_c"})
        backend = SopsBackend(secrets_file="/tmp/fake.enc.yaml")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=decrypted, stderr=""
            )
            keys = backend.list_keys()

        assert sorted(keys) == ["KEY_A", "KEY_B", "KEY_C"]

    def test_list_keys_empty_file(self):
        from himitsubako.backends.sops import SopsBackend

        decrypted = yaml.dump({})
        backend = SopsBackend(secrets_file="/tmp/fake.enc.yaml")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=decrypted, stderr=""
            )
            keys = backend.list_keys()

        assert keys == []

    def test_list_keys_file_not_found(self):
        from himitsubako.backends.sops import SopsBackend
        from himitsubako.errors import BackendError

        backend = SopsBackend(secrets_file="/tmp/nonexistent.enc.yaml")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=2,
                stdout="",
                stderr="Error: no such file",
            )
            with pytest.raises(BackendError):
                backend.list_keys()


class TestSopsBackendBinResolution:
    """AC-1: HIMITSUBAKO_SOPS_BIN env var > sops_bin arg > 'sops' on PATH."""

    def test_default_bin_is_sops_on_path(self, monkeypatch):
        from himitsubako.backends.sops import SopsBackend

        monkeypatch.delenv("HIMITSUBAKO_SOPS_BIN", raising=False)
        backend = SopsBackend(secrets_file="/tmp/fake.enc.yaml")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="{}\n", stderr="")
            backend.get("ANY")

        called_argv = mock_run.call_args.args[0]
        assert called_argv[0] == "sops"

    def test_explicit_bin_arg_used_when_no_env(self, monkeypatch, tmp_path):
        from himitsubako.backends.sops import SopsBackend

        monkeypatch.delenv("HIMITSUBAKO_SOPS_BIN", raising=False)
        fake_bin = tmp_path / "my-sops"
        fake_bin.write_text("#!/bin/sh\necho '{}'\n")
        fake_bin.chmod(0o755)

        backend = SopsBackend(
            secrets_file="/tmp/fake.enc.yaml", sops_bin=str(fake_bin)
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="{}\n", stderr="")
            backend.get("ANY")

        called_argv = mock_run.call_args.args[0]
        assert called_argv[0] == str(fake_bin)

    def test_env_var_overrides_constructor_arg(self, monkeypatch, tmp_path):
        from himitsubako.backends.sops import SopsBackend

        env_bin = tmp_path / "env-sops"
        env_bin.write_text("#!/bin/sh\necho '{}'\n")
        env_bin.chmod(0o755)
        ctor_bin = tmp_path / "ctor-sops"
        ctor_bin.write_text("#!/bin/sh\necho '{}'\n")
        ctor_bin.chmod(0o755)

        monkeypatch.setenv("HIMITSUBAKO_SOPS_BIN", str(env_bin))
        backend = SopsBackend(
            secrets_file="/tmp/fake.enc.yaml", sops_bin=str(ctor_bin)
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="{}\n", stderr="")
            backend.get("ANY")

        called_argv = mock_run.call_args.args[0]
        assert called_argv[0] == str(env_bin)

    def test_explicit_bin_missing_raises_backend_error(self, monkeypatch):
        from himitsubako.backends.sops import SopsBackend
        from himitsubako.errors import BackendError

        monkeypatch.delenv("HIMITSUBAKO_SOPS_BIN", raising=False)
        backend = SopsBackend(
            secrets_file="/tmp/fake.enc.yaml", sops_bin="/nonexistent/sops-bin"
        )

        with pytest.raises(BackendError, match=r"/nonexistent/sops-bin"):
            backend.get("ANY")


class TestSopsBackendTimeout:
    """AC-2: subprocess timeouts caught and re-raised as BackendError."""

    def test_decrypt_timeout_raises_backend_error(self):
        from himitsubako.backends.sops import SopsBackend
        from himitsubako.errors import BackendError

        backend = SopsBackend(secrets_file="/tmp/fake.enc.yaml")

        with (
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=["sops"], timeout=30),
            ),
            pytest.raises(BackendError, match=r"decrypt.*timed out"),
        ):
            backend.get("ANY")

    def test_encrypt_timeout_raises_backend_error_and_cleans_temp(self, tmp_path):
        from himitsubako.backends.sops import SopsBackend
        from himitsubako.errors import BackendError

        secrets_file = tmp_path / ".secrets.enc.yaml"
        backend = SopsBackend(secrets_file=str(secrets_file))

        decrypted_empty = yaml.dump({})

        def fake_run(*args, **kwargs):
            argv = args[0]
            if "--decrypt" in argv:
                return MagicMock(returncode=0, stdout=decrypted_empty, stderr="")
            raise subprocess.TimeoutExpired(cmd=argv, timeout=30)

        with (
            patch("subprocess.run", side_effect=fake_run),
            pytest.raises(BackendError, match=r"encrypt.*timed out"),
        ):
            backend.set("KEY", "value")

        leftover = list(tmp_path.glob("*.yaml"))
        assert leftover == [], f"temp files not cleaned up: {leftover}"


class TestSopsBackendFilenameOverride:
    """Regression guard: encrypt argv must pass --filename-override with the
    real target filename so sops applies creation_rules to the target, not
    the mkstemp-generated tempfile name. Discovered by HMB-S013 integration
    tests; latent bug in v0.1.0 through v0.2.0."""

    def test_encrypt_argv_passes_filename_override_target(self, tmp_path):
        from himitsubako.backends.sops import SopsBackend

        secrets_file = tmp_path / ".secrets.enc.yaml"
        backend = SopsBackend(secrets_file=str(secrets_file))

        decrypted_empty = yaml.dump({})
        captured: list[list[str]] = []

        def fake_run(*args, **kwargs):
            argv = list(args[0])
            captured.append(argv)
            if "--decrypt" in argv:
                return MagicMock(returncode=0, stdout=decrypted_empty, stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            backend.set("KEY", "value")

        encrypt_calls = [a for a in captured if "--encrypt" in a]
        assert encrypt_calls, "expected at least one sops --encrypt call"
        argv = encrypt_calls[0]
        assert "--filename-override" in argv, argv
        override_idx = argv.index("--filename-override")
        assert argv[override_idx + 1] == str(secrets_file), (
            "--filename-override must carry the real target path, not the tempfile"
        )
        # --filename-override must come before --in-place so sops parses
        # the override value as the flag argument, not as a positional.
        inplace_idx = argv.index("--in-place")
        assert override_idx < inplace_idx, (
            f"--filename-override must precede --in-place in argv: {argv}"
        )
        # --in-place is immediately followed by the tempfile positional.
        positional = argv[inplace_idx + 1]
        assert positional != str(secrets_file)
        assert Path(positional).parent == secrets_file.parent


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes only")
class TestSopsBackendFilePermissions:
    """AC-3: .secrets.enc.yaml is mode 0600 after writes regardless of umask."""

    def test_new_secrets_file_is_mode_0600(self, tmp_path):
        from himitsubako.backends.sops import SopsBackend

        secrets_file = tmp_path / ".secrets.enc.yaml"
        backend = SopsBackend(secrets_file=str(secrets_file))

        decrypted_empty = yaml.dump({})

        def fake_run(*args, **kwargs):
            argv = args[0]
            if "--decrypt" in argv:
                return MagicMock(returncode=0, stdout=decrypted_empty, stderr="")
            # Encrypt in place: leave the temp file where it is; backend renames it.
            return MagicMock(returncode=0, stdout="", stderr="")

        old_umask = os.umask(0o022)
        try:
            with patch("subprocess.run", side_effect=fake_run):
                backend.set("KEY", "value")
        finally:
            os.umask(old_umask)

        assert secrets_file.exists()
        mode = stat.S_IMODE(secrets_file.stat().st_mode)
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"

    def test_existing_secrets_file_rewritten_to_0600(self, tmp_path):
        from himitsubako.backends.sops import SopsBackend

        secrets_file = tmp_path / ".secrets.enc.yaml"
        secrets_file.write_text("placeholder")
        secrets_file.chmod(0o644)
        backend = SopsBackend(secrets_file=str(secrets_file))

        decrypted = yaml.dump({"OLD": "v"})

        def fake_run(*args, **kwargs):
            argv = args[0]
            if "--decrypt" in argv:
                return MagicMock(returncode=0, stdout=decrypted, stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        old_umask = os.umask(0o022)
        try:
            with patch("subprocess.run", side_effect=fake_run):
                backend.set("NEW", "v2")
        finally:
            os.umask(old_umask)

        mode = stat.S_IMODE(secrets_file.stat().st_mode)
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"
