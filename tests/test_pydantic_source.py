"""Tests for HimitsubakoSettingsSource (HMB-S011)."""

from __future__ import annotations

import pytest


class _StubBackend:
    def __init__(self, store: dict[str, str]) -> None:
        self._store = store

    @property
    def backend_name(self) -> str:
        return "stub"

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:  # pragma: no cover
        self._store[key] = value

    def delete(self, key: str) -> None:  # pragma: no cover
        self._store.pop(key, None)

    def list_keys(self) -> list[str]:  # pragma: no cover
        return list(self._store.keys())


class TestHimitsubakoSettingsSourceLookup:
    def test_resolves_field_from_backend(self):
        from pydantic_settings import BaseSettings

        from himitsubako.pydantic import HimitsubakoSettingsSource

        backend = _StubBackend({"DB_PASSWORD": "from_himitsubako"})

        class Settings(BaseSettings):
            DB_PASSWORD: str = "default_value"

        source = HimitsubakoSettingsSource(Settings, backend=backend)
        values = source()
        assert values.get("DB_PASSWORD") == "from_himitsubako"

    def test_missing_field_returns_none_in_dict(self):
        from pydantic_settings import BaseSettings

        from himitsubako.pydantic import HimitsubakoSettingsSource

        backend = _StubBackend({})

        class Settings(BaseSettings):
            API_KEY: str = "default"

        source = HimitsubakoSettingsSource(Settings, backend=backend)
        values = source()
        # Missing fields are absent from the returned dict so other sources
        # in the chain can provide them.
        assert "API_KEY" not in values

    def test_prefix_prepends_to_field_name(self):
        from pydantic_settings import BaseSettings

        from himitsubako.pydantic import HimitsubakoSettingsSource

        backend = _StubBackend({"MYAPP_DB_PASSWORD": "with_prefix"})

        class Settings(BaseSettings):
            DB_PASSWORD: str = ""

        source = HimitsubakoSettingsSource(
            Settings, backend=backend, prefix="MYAPP_"
        )
        values = source()
        assert values.get("DB_PASSWORD") == "with_prefix"


class TestHimitsubakoSettingsSourceImportError:
    def test_import_error_raises_clear_backend_error(self, monkeypatch):
        """Simulate pydantic-settings missing by patching the import."""
        import sys

        from himitsubako import pydantic as pyd_module

        # Force the import to fail by removing the module and re-importing
        monkeypatch.setattr(
            pyd_module, "_PYDANTIC_SETTINGS_AVAILABLE", False
        )
        monkeypatch.setattr(
            pyd_module, "_PYDANTIC_SETTINGS_IMPORT_ERROR", ImportError("nope")
        )

        from himitsubako.errors import BackendError
        from himitsubako.pydantic import HimitsubakoSettingsSource

        with pytest.raises(BackendError, match=r"\[pydantic-settings\]"):
            HimitsubakoSettingsSource(object)

        # Restore for other tests in the session
        sys.modules.pop("himitsubako.pydantic", None)
