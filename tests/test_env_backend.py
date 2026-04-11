"""Tests for the environment variable backend (HMB-S007)."""

from __future__ import annotations

import os

import pytest

from himitsubako.backends.protocol import SecretBackend


def _scrub_prefix(monkeypatch, prefix: str) -> None:
    """Remove every host env var matching prefix so tests are hermetic."""
    for name in [k for k in os.environ if k.startswith(prefix)]:
        monkeypatch.delenv(name, raising=False)


class TestEnvBackendProtocol:
    """The env backend conforms to the SecretBackend protocol."""

    def test_conforms_to_protocol(self):
        from himitsubako.backends.env import EnvBackend

        backend = EnvBackend()
        assert isinstance(backend, SecretBackend)

    def test_backend_name(self):
        from himitsubako.backends.env import EnvBackend

        assert EnvBackend().backend_name == "env"


class TestEnvBackendGet:
    """get() reads from os.environ, optionally with a prefix."""

    def test_get_existing_key_no_prefix(self, monkeypatch):
        from himitsubako.backends.env import EnvBackend

        monkeypatch.setenv("PLAIN_KEY", "plain_value")
        backend = EnvBackend()

        assert backend.get("PLAIN_KEY") == "plain_value"

    def test_get_missing_key_returns_none(self, monkeypatch):
        from himitsubako.backends.env import EnvBackend

        monkeypatch.delenv("DEFINITELY_NOT_SET", raising=False)
        backend = EnvBackend()

        assert backend.get("DEFINITELY_NOT_SET") is None

    def test_get_with_prefix_prepends(self, monkeypatch):
        from himitsubako.backends.env import EnvBackend

        _scrub_prefix(monkeypatch, "MYAPP_")
        monkeypatch.setenv("MYAPP_DB_PASSWORD", "supersecret")
        monkeypatch.delenv("DB_PASSWORD", raising=False)
        backend = EnvBackend(prefix="MYAPP_")

        assert backend.get("DB_PASSWORD") == "supersecret"

    def test_get_with_prefix_does_not_match_unprefixed_var(self, monkeypatch):
        from himitsubako.backends.env import EnvBackend

        _scrub_prefix(monkeypatch, "MYAPP_")
        monkeypatch.setenv("DB_PASSWORD", "naked_value")
        backend = EnvBackend(prefix="MYAPP_")

        assert backend.get("DB_PASSWORD") is None

    def test_get_reads_environment_lazily(self, monkeypatch):
        """Backend stores no values; each get() reads os.environ fresh."""
        from himitsubako.backends.env import EnvBackend

        backend = EnvBackend()
        monkeypatch.delenv("LATE_BOUND", raising=False)
        assert backend.get("LATE_BOUND") is None

        monkeypatch.setenv("LATE_BOUND", "now_set")
        assert backend.get("LATE_BOUND") == "now_set"


class TestEnvBackendReadOnly:
    """set() and delete() raise BackendError; env vars are set externally."""

    def test_set_raises_backend_error(self):
        from himitsubako.backends.env import EnvBackend
        from himitsubako.errors import BackendError

        backend = EnvBackend()
        with pytest.raises(BackendError, match=r"read-only"):
            backend.set("ANY_KEY", "any_value")

    def test_delete_raises_backend_error(self):
        from himitsubako.backends.env import EnvBackend
        from himitsubako.errors import BackendError

        backend = EnvBackend()
        with pytest.raises(BackendError, match=r"read-only"):
            backend.delete("ANY_KEY")

    def test_set_does_not_actually_modify_environment(self, monkeypatch):
        """Even if set() raised, os.environ must be untouched."""
        from himitsubako.backends.env import EnvBackend
        from himitsubako.errors import BackendError

        monkeypatch.delenv("UNTOUCHED_KEY", raising=False)
        backend = EnvBackend()

        with pytest.raises(BackendError):
            backend.set("UNTOUCHED_KEY", "value")

        assert "UNTOUCHED_KEY" not in os.environ


class TestEnvBackendListKeys:
    """list_keys() returns env vars; with a prefix it filters and strips it."""

    def test_list_keys_no_prefix_includes_environment(self, monkeypatch):
        from himitsubako.backends.env import EnvBackend

        monkeypatch.setenv("HMB_TEST_LIST_A", "1")
        monkeypatch.setenv("HMB_TEST_LIST_B", "2")
        backend = EnvBackend()

        keys = backend.list_keys()
        assert "HMB_TEST_LIST_A" in keys
        assert "HMB_TEST_LIST_B" in keys

    def test_list_keys_with_prefix_filters_and_strips(self, monkeypatch):
        from himitsubako.backends.env import EnvBackend

        _scrub_prefix(monkeypatch, "MYAPP_")
        monkeypatch.setenv("MYAPP_DB_PASSWORD", "x")
        monkeypatch.setenv("MYAPP_API_KEY", "y")
        monkeypatch.setenv("UNRELATED_VAR", "z")
        backend = EnvBackend(prefix="MYAPP_")

        keys = backend.list_keys()
        assert sorted(keys) == ["API_KEY", "DB_PASSWORD"]
        assert "UNRELATED_VAR" not in keys

    def test_list_keys_with_prefix_no_matches_returns_empty(self, monkeypatch):
        from himitsubako.backends.env import EnvBackend

        _scrub_prefix(monkeypatch, "ZZNOMATCH_")
        backend = EnvBackend(prefix="ZZNOMATCH_")

        assert backend.list_keys() == []
