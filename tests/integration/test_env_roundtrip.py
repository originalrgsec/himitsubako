"""HMB-S013: env backend integration tests.

These tests do not require sops or age, but they live in the integration
suite alongside the SOPS tests because they exercise the full
`load_config` → `BackendRouter` → `EnvBackend` path against a real
filesystem and a real `os.environ`.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
import yaml

if TYPE_CHECKING:
    from pathlib import Path

from himitsubako.backends.env import EnvBackend
from himitsubako.config import find_config, load_config
from himitsubako.errors import BackendError
from himitsubako.router import BackendRouter

pytestmark = pytest.mark.integration


def _write_env_config(project_dir: Path, prefix: str) -> None:
    (project_dir / ".himitsubako.yaml").write_text(
        yaml.safe_dump(
            {"default_backend": "env", "env": {"prefix": prefix}}
        )
    )


class TestEnvPrefixFiltering:
    def test_get_with_prefix_reads_real_environ(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MYAPP_DB_PASSWORD", "real-env-value")
        _write_env_config(tmp_path, prefix="MYAPP_")
        monkeypatch.chdir(tmp_path)

        config_path = find_config(tmp_path)
        assert config_path is not None
        config = load_config(config_path)
        router = BackendRouter(config, project_dir=tmp_path)

        assert router.get("DB_PASSWORD") == "real-env-value"

    def test_list_with_prefix_strips_prefix_from_real_environ(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for k in [k for k in os.environ if k.startswith("TESTAPP_")]:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("TESTAPP_API_KEY", "x")
        monkeypatch.setenv("TESTAPP_TOKEN", "y")

        backend = EnvBackend(prefix="TESTAPP_")
        keys = set(backend.list_keys())
        assert {"API_KEY", "TOKEN"}.issubset(keys)

    def test_missing_env_var_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DOES_NOT_EXIST_HMB_INT", raising=False)
        backend = EnvBackend()
        assert backend.get("DOES_NOT_EXIST_HMB_INT") is None


class TestEnvFallbackChain:
    """No .himitsubako.yaml → fallback chain lands on the env backend."""

    def test_no_config_yields_env_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Use a deeper subdir and pass stop_at=tmp_path so find_config
        # cannot accidentally hit a .himitsubako.yaml higher in the
        # developer's workspace ancestry.
        empty = tmp_path / "empty-project"
        empty.mkdir()
        monkeypatch.chdir(empty)
        assert find_config(empty, stop_at=tmp_path) is None

        # The high-level API should still resolve env values.
        monkeypatch.setenv("HMB_INTEGRATION_FALLBACK_KEY", "from-env")
        from himitsubako.api import get

        assert get("HMB_INTEGRATION_FALLBACK_KEY") == "from-env"


class TestEnvReadOnly:
    def test_set_raises_backend_error(self) -> None:
        backend = EnvBackend()
        with pytest.raises(BackendError, match="read-only"):
            backend.set("ANY", "value")

    def test_delete_raises_backend_error(self) -> None:
        backend = EnvBackend()
        with pytest.raises(BackendError, match="read-only"):
            backend.delete("ANY")
