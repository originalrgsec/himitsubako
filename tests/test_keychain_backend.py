"""Tests for the macOS Keychain backend (HMB-S008)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from himitsubako.backends.protocol import SecretBackend


class TestKeychainBackendProtocol:
    def test_conforms_to_protocol(self):
        from himitsubako.backends.keychain import KeychainBackend

        backend = KeychainBackend(service="myapp")
        assert isinstance(backend, SecretBackend)

    def test_backend_name(self):
        from himitsubako.backends.keychain import KeychainBackend

        assert KeychainBackend(service="myapp").backend_name == "keychain"


class TestKeychainBackendImportError:
    def test_get_raises_clear_error_when_keyring_missing(self):
        from himitsubako.backends.keychain import KeychainBackend
        from himitsubako.errors import BackendError

        backend = KeychainBackend(service="myapp")
        # Force the lazy import to fail by patching the helper
        with (
            patch.object(
                backend, "_import_keyring", side_effect=ImportError("no keyring")
            ),
            pytest.raises(BackendError, match=r"\[keychain\]"),
        ):
            backend.get("ANY")


class TestKeychainBackendDenyList:
    """T-023 / M-015: refuse insecure default backends."""

    def _patch_keyring(self, class_name: str):
        fake_module = MagicMock()
        fake_keyring_obj = MagicMock()
        fake_keyring_obj.__class__.__name__ = class_name
        fake_module.get_keyring.return_value = fake_keyring_obj
        return fake_module

    def test_null_keyring_rejected(self):
        from himitsubako.backends.keychain import KeychainBackend
        from himitsubako.errors import BackendError

        fake = self._patch_keyring("Null")
        backend = KeychainBackend(service="myapp")
        with (
            patch.object(backend, "_import_keyring", return_value=fake),
            pytest.raises(BackendError, match=r"insecure backend"),
        ):
            backend.get("ANY")

    def test_plaintext_keyring_rejected(self):
        from himitsubako.backends.keychain import KeychainBackend
        from himitsubako.errors import BackendError

        fake = self._patch_keyring("PlaintextKeyring")
        backend = KeychainBackend(service="myapp")
        with (
            patch.object(backend, "_import_keyring", return_value=fake),
            pytest.raises(BackendError, match=r"insecure backend"),
        ):
            backend.set("ANY", "value")

    def test_macos_keyring_accepted(self):
        from himitsubako.backends.keychain import KeychainBackend

        fake = MagicMock()
        macos_kr = MagicMock()
        macos_kr.__class__.__name__ = "Keyring"  # macOS keychain class name
        fake.get_keyring.return_value = macos_kr
        fake.get_password.return_value = "actual_value"

        backend = KeychainBackend(service="myapp")
        with patch.object(backend, "_import_keyring", return_value=fake):
            assert backend.get("ANY") == "actual_value"


class TestKeychainBackendCRUD:
    def _ok_keyring(self):
        fake = MagicMock()
        macos_kr = MagicMock()
        macos_kr.__class__.__name__ = "Keyring"
        fake.get_keyring.return_value = macos_kr
        return fake

    def test_get_returns_value(self):
        from himitsubako.backends.keychain import KeychainBackend

        fake = self._ok_keyring()
        fake.get_password.return_value = "secret_value"

        backend = KeychainBackend(service="myapp")
        with patch.object(backend, "_import_keyring", return_value=fake):
            assert backend.get("DB_PASSWORD") == "secret_value"

        fake.get_password.assert_called_once_with("myapp", "DB_PASSWORD")

    def test_get_returns_none_when_missing(self):
        from himitsubako.backends.keychain import KeychainBackend

        fake = self._ok_keyring()
        fake.get_password.return_value = None

        backend = KeychainBackend(service="myapp")
        with patch.object(backend, "_import_keyring", return_value=fake):
            assert backend.get("MISSING") is None

    def test_set_stores_value(self):
        from himitsubako.backends.keychain import KeychainBackend

        fake = self._ok_keyring()
        backend = KeychainBackend(service="myapp")
        with patch.object(backend, "_import_keyring", return_value=fake):
            backend.set("NEW_KEY", "new_value")

        fake.set_password.assert_called_once_with("myapp", "NEW_KEY", "new_value")

    def test_delete_removes_value(self):
        from himitsubako.backends.keychain import KeychainBackend

        fake = self._ok_keyring()
        backend = KeychainBackend(service="myapp")
        with patch.object(backend, "_import_keyring", return_value=fake):
            backend.delete("OLD_KEY")

        fake.delete_password.assert_called_once_with("myapp", "OLD_KEY")

    def test_delete_missing_raises_secret_not_found(self):
        from himitsubako.backends.keychain import KeychainBackend
        from himitsubako.errors import SecretNotFoundError

        fake = self._ok_keyring()

        # Build a fake PasswordDeleteError class that the backend will catch.
        class FakePasswordDeleteError(Exception):
            pass

        fake.errors = MagicMock()
        fake.errors.PasswordDeleteError = FakePasswordDeleteError
        fake.errors.KeyringError = Exception  # parent class
        fake.delete_password.side_effect = FakePasswordDeleteError("nope")

        backend = KeychainBackend(service="myapp")
        with (
            patch.object(backend, "_import_keyring", return_value=fake),
            pytest.raises(SecretNotFoundError),
        ):
            backend.delete("NEVER_EXISTED")


class TestKeychainBackendListKeysRaises:
    """Decision 4: list_keys raises rather than returning empty."""

    def test_list_keys_always_raises_backend_error(self):
        from himitsubako.backends.keychain import KeychainBackend
        from himitsubako.errors import BackendError

        backend = KeychainBackend(service="myapp")
        with pytest.raises(BackendError, match=r"list_keys not supported"):
            backend.list_keys()
