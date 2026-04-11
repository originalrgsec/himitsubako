"""Tests for the HimitsubakoConfig model."""

from __future__ import annotations

import pytest
import yaml


class TestHimitsubakoConfig:
    """Verify config model parsing and validation."""

    def test_config_is_importable(self):
        from himitsubako.config import HimitsubakoConfig

        assert HimitsubakoConfig is not None

    def test_default_config_has_sops_backend(self):
        from himitsubako.config import HimitsubakoConfig

        config = HimitsubakoConfig()
        assert config.default_backend == "sops"

    def test_config_from_yaml_string(self):
        from himitsubako.config import HimitsubakoConfig

        raw = {
            "default_backend": "env",
            "sops": {"secrets_file": ".secrets.enc.yaml"},
        }
        config = HimitsubakoConfig(**raw)
        assert config.default_backend == "env"

    def test_config_from_file(self, tmp_path):
        from himitsubako.config import load_config

        config_file = tmp_path / ".himitsubako.yaml"
        config_file.write_text(
            yaml.dump({"default_backend": "keychain", "keychain": {"service": "myapp"}})
        )
        config = load_config(config_file)
        assert config.default_backend == "keychain"

    def test_config_rejects_unknown_backend(self):
        from himitsubako.config import HimitsubakoConfig

        with pytest.raises(ValueError, match=r"unknown.*backend|not.*valid"):
            HimitsubakoConfig(default_backend="nosuchbackend")

    def test_config_sops_defaults(self):
        from himitsubako.config import HimitsubakoConfig

        config = HimitsubakoConfig()
        assert config.sops.secrets_file == ".secrets.enc.yaml"
        assert config.sops.bin is None

    def test_config_sops_bin_override(self):
        from himitsubako.config import HimitsubakoConfig

        config = HimitsubakoConfig(**{"sops": {"bin": "/opt/homebrew/bin/sops"}})
        assert config.sops.bin == "/opt/homebrew/bin/sops"

    def test_config_is_immutable(self):
        from himitsubako.config import HimitsubakoConfig

        config = HimitsubakoConfig()
        with pytest.raises((TypeError, ValueError)):
            config.default_backend = "env"  # type: ignore[misc]

    def test_load_config_missing_file_raises(self, tmp_path):
        from himitsubako.config import load_config
        from himitsubako.errors import ConfigError

        with pytest.raises(ConfigError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_load_config_invalid_yaml_raises(self, tmp_path):
        from himitsubako.config import load_config
        from himitsubako.errors import ConfigError

        bad_file = tmp_path / ".himitsubako.yaml"
        bad_file.write_text(": : : not valid yaml [[[")
        with pytest.raises(ConfigError):
            load_config(bad_file)

    def test_find_config_walks_up(self, tmp_path):
        from himitsubako.config import find_config

        # Place config in parent, search from child
        config_file = tmp_path / ".himitsubako.yaml"
        config_file.write_text(yaml.dump({"default_backend": "sops"}))
        child = tmp_path / "subdir" / "deep"
        child.mkdir(parents=True)

        found = find_config(child)
        assert found is not None
        assert found == config_file

    def test_find_config_returns_none_when_missing(self, tmp_path):
        from himitsubako.config import find_config

        # tmp_path has no .himitsubako.yaml
        # Create an isolated directory with no config anywhere
        isolated = tmp_path / "isolated"
        isolated.mkdir()
        found = find_config(isolated, stop_at=tmp_path)
        assert found is None
