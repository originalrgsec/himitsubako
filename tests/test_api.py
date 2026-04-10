"""Tests for the top-level himitsubako Python API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import yaml


class TestPublicApi:
    """Test himitsubako.get(), himitsubako.set_secret(), himitsubako.list_secrets()."""

    def test_get_is_importable(self):
        from himitsubako import get

        assert callable(get)

    def test_set_secret_is_importable(self):
        from himitsubako import set_secret

        assert callable(set_secret)

    def test_list_secrets_is_importable(self):
        from himitsubako import list_secrets

        assert callable(list_secrets)

    def test_get_returns_value_from_sops_backend(self, tmp_path, monkeypatch):
        from himitsubako import get

        config_file = tmp_path / ".himitsubako.yaml"
        config_file.write_text(
            yaml.dump({"default_backend": "sops", "sops": {"secrets_file": ".secrets.enc.yaml"}})
        )
        monkeypatch.chdir(tmp_path)

        decrypted = yaml.dump({"MY_KEY": "my_value"})
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=decrypted, stderr="")
            result = get("MY_KEY")

        assert result == "my_value"

    def test_get_returns_none_for_missing_key(self, tmp_path, monkeypatch):
        from himitsubako import get

        config_file = tmp_path / ".himitsubako.yaml"
        config_file.write_text(
            yaml.dump({"default_backend": "sops", "sops": {"secrets_file": ".secrets.enc.yaml"}})
        )
        monkeypatch.chdir(tmp_path)

        decrypted = yaml.dump({"OTHER": "val"})
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=decrypted, stderr="")
            result = get("NONEXISTENT")

        assert result is None

    def test_set_secret_stores_value(self, tmp_path, monkeypatch):
        from himitsubako import set_secret

        config_file = tmp_path / ".himitsubako.yaml"
        config_file.write_text(
            yaml.dump({"default_backend": "sops", "sops": {"secrets_file": ".secrets.enc.yaml"}})
        )
        monkeypatch.chdir(tmp_path)

        decrypted = yaml.dump({})
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=decrypted, stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
            ]
            set_secret("NEW_KEY", "new_val")

        assert mock_run.call_count == 2

    def test_list_secrets_returns_keys(self, tmp_path, monkeypatch):
        from himitsubako import list_secrets

        config_file = tmp_path / ".himitsubako.yaml"
        config_file.write_text(
            yaml.dump({"default_backend": "sops", "sops": {"secrets_file": ".secrets.enc.yaml"}})
        )
        monkeypatch.chdir(tmp_path)

        decrypted = yaml.dump({"A": "1", "B": "2"})
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=decrypted, stderr="")
            result = list_secrets()

        assert sorted(result) == ["A", "B"]

    def test_get_falls_back_to_env(self, tmp_path, monkeypatch):
        """When no config files exist, get() should fall back to env backend."""
        from himitsubako import get

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("MY_ENV_KEY", "env_value")

        result = get("MY_ENV_KEY")
        assert result == "env_value"

    def test_get_env_fallback_returns_none(self, tmp_path, monkeypatch):
        from himitsubako import get

        monkeypatch.chdir(tmp_path)

        result = get("DEFINITELY_NOT_SET_ABC123")
        assert result is None
