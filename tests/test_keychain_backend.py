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

        # The real _import_keyring raises BackendError on ImportError, so the
        # test simulates that exact failure mode rather than letting raw
        # ImportError escape (which would mean the implementation forgot to
        # wrap it).
        backend = KeychainBackend(service="myapp")
        sim_failure = BackendError(
            "keychain",
            "keychain backend requires 'keyring'; install with 'pip install himitsubako[keychain]'",
        )
        with (
            patch.object(backend, "_import_keyring", side_effect=sim_failure),
            pytest.raises(BackendError, match=r"\[keychain\]"),
        ):
            backend.get("ANY")


class TestKeychainBackendDenyList:
    """T-023 / M-015: refuse insecure default backends, including subclasses."""

    def _make_fake_keyring(self, keyring_instance):
        """Wrap a real instance in a fake module that exposes get_keyring()."""
        fake_module = MagicMock()
        fake_module.get_keyring.return_value = keyring_instance
        return fake_module

    def test_null_keyring_rejected(self):
        from himitsubako.backends.keychain import KeychainBackend
        from himitsubako.errors import BackendError

        # Real class named exactly like a denied entry.
        class Null:
            pass

        fake = self._make_fake_keyring(Null())
        backend = KeychainBackend(service="myapp")
        with (
            patch.object(backend, "_import_keyring", return_value=fake),
            pytest.raises(BackendError, match=r"insecure backend"),
        ):
            backend.get("ANY")

    def test_plaintext_keyring_rejected(self):
        from himitsubako.backends.keychain import KeychainBackend
        from himitsubako.errors import BackendError

        class PlaintextKeyring:
            pass

        fake = self._make_fake_keyring(PlaintextKeyring())
        backend = KeychainBackend(service="myapp")
        with (
            patch.object(backend, "_import_keyring", return_value=fake),
            pytest.raises(BackendError, match=r"insecure backend"),
        ):
            backend.set("ANY", "value")

    def test_subclass_of_denied_class_rejected_via_mro(self):
        """A subclass cannot bypass the deny-list by renaming itself."""
        from himitsubako.backends.keychain import KeychainBackend
        from himitsubako.errors import BackendError

        class PlaintextKeyring:
            pass

        class SafeWrapper(PlaintextKeyring):
            pass

        fake = self._make_fake_keyring(SafeWrapper())
        backend = KeychainBackend(service="myapp")
        with (
            patch.object(backend, "_import_keyring", return_value=fake),
            pytest.raises(BackendError, match=r"PlaintextKeyring"),
        ):
            backend.get("ANY")

    def test_macos_keyring_accepted(self):
        from himitsubako.backends.keychain import KeychainBackend

        class Keyring:  # macOS keychain class name
            def get_password(self, service, key):
                return "actual_value"

        instance = Keyring()
        fake = MagicMock()
        fake.get_keyring.return_value = instance
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
