"""Tests for BackendRouter (HMB-S012)."""

from __future__ import annotations

from pathlib import Path

import pytest

from himitsubako.backends.protocol import SecretBackend
from himitsubako.config import HimitsubakoConfig


class _StubBackend:
    """Test double that records calls and returns canned values."""

    def __init__(self, name: str, store: dict[str, str] | None = None) -> None:
        self._name = name
        self._store: dict[str, str] = dict(store or {})
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, str]] = []
        self.delete_calls: list[str] = []
        self.list_raises: bool = False

    @property
    def backend_name(self) -> str:
        return self._name

    def get(self, key: str) -> str | None:
        self.get_calls.append(key)
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        self.set_calls.append((key, value))
        self._store[key] = value

    def delete(self, key: str) -> None:
        self.delete_calls.append(key)
        self._store.pop(key, None)

    def list_keys(self) -> list[str]:
        if self.list_raises:
            from himitsubako.errors import BackendError

            raise BackendError(self._name, "list not supported")
        return list(self._store.keys())


def _make_router(config: HimitsubakoConfig, backends: dict[str, SecretBackend]):
    """Build a router with hand-rolled backend stubs (no factory)."""
    from himitsubako.router import BackendRouter

    router = BackendRouter(config, project_dir=Path("/tmp/fake"))
    router._cache = backends
    return router


class TestRouterProtocol:
    def test_implements_secret_backend_protocol(self):
        from himitsubako.router import BackendRouter

        cfg = HimitsubakoConfig()
        router = BackendRouter(cfg, project_dir=Path("/tmp/fake"))
        assert isinstance(router, SecretBackend)

    def test_backend_name_is_router(self):
        from himitsubako.router import BackendRouter

        cfg = HimitsubakoConfig()
        router = BackendRouter(cfg, project_dir=Path("/tmp/fake"))
        assert router.backend_name == "router"


class TestRouterResolution:
    def test_no_credentials_section_uses_default(self):
        cfg = HimitsubakoConfig(default_backend="sops")
        sops = _StubBackend("sops")
        router = _make_router(cfg, {"sops": sops})

        resolved = router.resolve("ANY_KEY")
        assert resolved is sops

    def test_exact_match_overrides_default(self):
        cfg = HimitsubakoConfig(
            default_backend="sops",
            credentials={"AWS_KEY": {"backend": "env"}},
        )
        sops = _StubBackend("sops")
        env = _StubBackend("env")
        router = _make_router(cfg, {"sops": sops, "env": env})

        assert router.resolve("AWS_KEY") is env
        assert router.resolve("OTHER_KEY") is sops

    def test_glob_match_routes(self):
        cfg = HimitsubakoConfig(
            default_backend="sops",
            credentials={"AWS_*": {"backend": "env"}},
        )
        sops = _StubBackend("sops")
        env = _StubBackend("env")
        router = _make_router(cfg, {"sops": sops, "env": env})

        assert router.resolve("AWS_ACCESS_KEY_ID") is env
        assert router.resolve("AWS_SECRET") is env
        assert router.resolve("UNRELATED") is sops

    def test_exact_wins_over_glob(self):
        cfg = HimitsubakoConfig(
            default_backend="sops",
            credentials={
                "AWS_*": {"backend": "env"},
                "AWS_SPECIAL": {"backend": "keychain"},
            },
        )
        sops = _StubBackend("sops")
        env = _StubBackend("env")
        keychain = _StubBackend("keychain")
        router = _make_router(
            cfg, {"sops": sops, "env": env, "keychain": keychain}
        )

        assert router.resolve("AWS_SPECIAL") is keychain
        assert router.resolve("AWS_OTHER") is env
        assert router.resolve("UNMATCHED") is sops

    def test_unknown_backend_in_credentials_rejected_by_config(self):
        with pytest.raises(ValueError, match=r"unknown backend"):
            HimitsubakoConfig(
                default_backend="sops",
                credentials={"K": {"backend": "nosuchbackend"}},
            )


class TestRouterDispatch:
    def test_get_routes_to_correct_backend(self):
        cfg = HimitsubakoConfig(
            default_backend="sops",
            credentials={"DB_PASSWORD": {"backend": "env"}},
        )
        sops = _StubBackend("sops", {"OTHER": "from_sops"})
        env = _StubBackend("env", {"DB_PASSWORD": "from_env"})
        router = _make_router(cfg, {"sops": sops, "env": env})

        assert router.get("DB_PASSWORD") == "from_env"
        assert router.get("OTHER") == "from_sops"
        assert env.get_calls == ["DB_PASSWORD"]
        assert sops.get_calls == ["OTHER"]

    def test_set_routes_to_correct_backend(self):
        cfg = HimitsubakoConfig(
            default_backend="sops",
            credentials={"NEW_KEY": {"backend": "env"}},
        )
        sops = _StubBackend("sops")
        env = _StubBackend("env")
        router = _make_router(cfg, {"sops": sops, "env": env})

        router.set("NEW_KEY", "value")
        assert env.set_calls == [("NEW_KEY", "value")]
        assert sops.set_calls == []

    def test_delete_routes_to_correct_backend(self):
        cfg = HimitsubakoConfig(
            default_backend="sops",
            credentials={"GO_AWAY": {"backend": "env"}},
        )
        sops = _StubBackend("sops")
        env = _StubBackend("env")
        router = _make_router(cfg, {"sops": sops, "env": env})

        router.delete("GO_AWAY")
        assert env.delete_calls == ["GO_AWAY"]


class TestRouterListKeys:
    def test_list_keys_aggregates_default_and_routed_backends(self):
        cfg = HimitsubakoConfig(
            default_backend="sops",
            credentials={
                "AWS_KEY": {"backend": "env"},
                "DB_PASSWORD": {"backend": "keychain"},
            },
        )
        sops = _StubBackend("sops", {"sops_only": "v"})
        env = _StubBackend("env", {"AWS_KEY": "v"})
        keychain = _StubBackend("keychain", {"DB_PASSWORD": "v"})
        router = _make_router(
            cfg, {"sops": sops, "env": env, "keychain": keychain}
        )

        keys = sorted(router.list_keys())
        assert "sops_only" in keys
        assert "AWS_KEY" in keys
        assert "DB_PASSWORD" in keys

    def test_list_keys_skips_backends_that_raise(self, capsys):
        cfg = HimitsubakoConfig(
            default_backend="sops",
            credentials={"K": {"backend": "keychain"}},
        )
        sops = _StubBackend("sops", {"sops_key": "v"})
        keychain = _StubBackend("keychain", {})
        keychain.list_raises = True
        router = _make_router(cfg, {"sops": sops, "keychain": keychain})

        keys = router.list_keys()
        assert "sops_key" in keys

        captured = capsys.readouterr()
        assert "keychain" in captured.err
        assert "skipped" in captured.err.lower() or "warning" in captured.err.lower()


class TestRouterCaching:
    def test_backend_instances_are_cached(self):
        """Multiple resolve() calls return the same instance."""
        from himitsubako.router import BackendRouter

        cfg = HimitsubakoConfig(default_backend="env")
        router = BackendRouter(cfg, project_dir=Path("/tmp/fake"))

        first = router.resolve("KEY_A")
        second = router.resolve("KEY_B")
        assert first is second
