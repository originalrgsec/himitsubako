"""Tests for the error type hierarchy."""

from __future__ import annotations


class TestErrorHierarchy:
    """Verify error types exist and inherit correctly."""

    def test_base_error_is_importable(self):
        from himitsubako.errors import HimitsubakoError

        assert issubclass(HimitsubakoError, Exception)

    def test_backend_error_inherits_from_base(self):
        from himitsubako.errors import BackendError, HimitsubakoError

        assert issubclass(BackendError, HimitsubakoError)

    def test_config_error_inherits_from_base(self):
        from himitsubako.errors import ConfigError, HimitsubakoError

        assert issubclass(ConfigError, HimitsubakoError)

    def test_secret_not_found_inherits_from_backend(self):
        from himitsubako.errors import BackendError, SecretNotFoundError

        assert issubclass(SecretNotFoundError, BackendError)

    def test_secret_not_found_stores_key_as_attribute(self):
        from himitsubako.errors import SecretNotFoundError

        err = SecretNotFoundError("MY_KEY")
        assert err.key == "MY_KEY"
        assert "MY_KEY" not in str(err)  # key names not leaked in messages

    def test_backend_error_contains_backend_name(self):
        from himitsubako.errors import BackendError

        err = BackendError("sops", "binary not found")
        assert "sops" in str(err)
        assert "binary not found" in str(err)

    def test_config_error_contains_path(self):
        from himitsubako.errors import ConfigError

        err = ConfigError("/path/to/.himitsubako.yaml", "invalid YAML")
        assert ".himitsubako.yaml" in str(err)
        assert "invalid YAML" in str(err)
