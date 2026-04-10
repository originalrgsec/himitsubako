"""Tests for the SOPS+age backend."""

from __future__ import annotations

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
