"""Tests for the Google OAuth composite backend (HMB-S030)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


class TestGoogleOAuthConfig:
    """AC-1: Config parsing for google-oauth credential type."""

    def test_parse_google_oauth_credential(self, tmp_path: Path) -> None:
        from himitsubako.config import load_config

        config_file = tmp_path / ".himitsubako.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "credentials": {
                        "google_drive": {
                            "backend": "google-oauth",
                            "storage_backend": "sops",
                            "scopes": [
                                "https://www.googleapis.com/auth/drive.file",
                                "https://www.googleapis.com/auth/drive.readonly",
                            ],
                            "keys": {
                                "client_id": "google_oauth_client_id",
                                "client_secret": "google_oauth_client_secret",
                                "refresh_token": "google_drive_refresh_token",
                            },
                        }
                    }
                }
            )
        )
        config = load_config(config_file)
        route = config.credentials["google_drive"]
        assert route.backend == "google-oauth"
        assert route.storage_backend == "sops"
        assert "drive.file" in route.scopes[0]
        assert route.keys["client_id"] == "google_oauth_client_id"

    def test_google_oauth_requires_storage_backend(self, tmp_path: Path) -> None:
        from himitsubako.config import load_config
        from himitsubako.errors import ConfigError

        config_file = tmp_path / ".himitsubako.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "credentials": {
                        "google_drive": {
                            "backend": "google-oauth",
                            "scopes": ["https://googleapis.com/auth/drive"],
                            "keys": {
                                "client_id": "cid",
                                "client_secret": "cs",
                                "refresh_token": "rt",
                            },
                        }
                    }
                }
            )
        )
        with pytest.raises(ConfigError, match="storage_backend"):
            load_config(config_file)

    def test_google_oauth_requires_all_three_keys(self, tmp_path: Path) -> None:
        from himitsubako.config import load_config
        from himitsubako.errors import ConfigError

        config_file = tmp_path / ".himitsubako.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "credentials": {
                        "google_drive": {
                            "backend": "google-oauth",
                            "storage_backend": "sops",
                            "scopes": ["https://googleapis.com/auth/drive"],
                            "keys": {
                                "client_id": "cid",
                                "client_secret": "cs",
                                # missing refresh_token
                            },
                        }
                    }
                }
            )
        )
        with pytest.raises(ConfigError, match="refresh_token"):
            load_config(config_file)

    def test_google_oauth_fields_rejected_on_non_oauth_backend(self, tmp_path: Path) -> None:
        """storage_backend/scopes/keys must only appear when backend=google-oauth."""
        from himitsubako.config import load_config
        from himitsubako.errors import ConfigError

        config_file = tmp_path / ".himitsubako.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "credentials": {
                        "some_key": {
                            "backend": "sops",
                            "scopes": ["irrelevant"],
                        }
                    }
                }
            )
        )
        with pytest.raises(ConfigError, match="only valid when backend"):
            load_config(config_file)


class TestGoogleOAuthBackend:
    """Unit tests for the GoogleOAuthBackend class."""

    def _make_backend(self, storage_stub):
        from himitsubako.backends.google_oauth import GoogleOAuthBackend

        return GoogleOAuthBackend(
            storage=storage_stub,
            credential_name="google_drive",
            keys={
                "client_id": "g_client_id",
                "client_secret": "g_client_secret",
                "refresh_token": "g_refresh_token",
            },
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )

    def test_get_returns_json_blob(self) -> None:
        """AC-4 backbone: get() returns the three secrets as JSON."""
        storage = MagicMock()
        storage.get.side_effect = lambda k: {
            "g_client_id": "cid-value",
            "g_client_secret": "secret-value",
            "g_refresh_token": "token-value",
        }[k]

        backend = self._make_backend(storage)
        raw = backend.get("google_drive")
        assert raw is not None
        parsed = json.loads(raw)
        assert parsed == {
            "client_id": "cid-value",
            "client_secret": "secret-value",
            "refresh_token": "token-value",
        }

    def test_get_raises_on_missing_underlying_key(self) -> None:
        """AC-3 backbone: missing constituent key surfaces as BackendError."""
        from himitsubako.errors import BackendError

        storage = MagicMock()
        storage.get.side_effect = lambda k: None if k == "g_refresh_token" else "v"

        backend = self._make_backend(storage)
        with pytest.raises(BackendError, match="refresh_token"):
            backend.get("google_drive")

    def test_get_wrong_key_name_returns_none(self) -> None:
        """Keys other than the configured credential name return None (not found)."""
        storage = MagicMock()
        backend = self._make_backend(storage)
        assert backend.get("some_other_key") is None

    def test_set_accepts_json_writes_all_three(self) -> None:
        """set() parses JSON value and writes each underlying secret."""
        storage = MagicMock()
        backend = self._make_backend(storage)
        payload = json.dumps(
            {
                "client_id": "new-cid",
                "client_secret": "new-secret",
                "refresh_token": "new-token",
            }
        )
        backend.set("google_drive", payload)

        storage.set.assert_any_call("g_client_id", "new-cid")
        storage.set.assert_any_call("g_client_secret", "new-secret")
        storage.set.assert_any_call("g_refresh_token", "new-token")
        assert storage.set.call_count == 3

    def test_set_rejects_non_json(self) -> None:
        from himitsubako.errors import BackendError

        storage = MagicMock()
        backend = self._make_backend(storage)
        with pytest.raises(BackendError, match="JSON"):
            backend.set("google_drive", "not-json")

    def test_set_rejects_incomplete_payload(self) -> None:
        from himitsubako.errors import BackendError

        storage = MagicMock()
        backend = self._make_backend(storage)
        partial = json.dumps({"client_id": "x", "client_secret": "y"})
        with pytest.raises(BackendError, match="refresh_token"):
            backend.set("google_drive", partial)

    def test_list_keys_returns_credential_name(self) -> None:
        storage = MagicMock()
        backend = self._make_backend(storage)
        assert backend.list_keys() == ["google_drive"]

    def test_backend_name(self) -> None:
        storage = MagicMock()
        backend = self._make_backend(storage)
        assert backend.backend_name == "google-oauth"

    def test_delete_removes_all_three(self) -> None:
        storage = MagicMock()
        backend = self._make_backend(storage)
        backend.delete("google_drive")
        storage.delete.assert_any_call("g_client_id")
        storage.delete.assert_any_call("g_client_secret")
        storage.delete.assert_any_call("g_refresh_token")


class TestGetCredentialsObject:
    """AC-2: backend returns a live google.oauth2.credentials.Credentials."""

    def test_get_credentials_returns_credentials_object(self) -> None:
        from google.oauth2.credentials import Credentials

        from himitsubako.backends.google_oauth import GoogleOAuthBackend

        storage = MagicMock()
        storage.get.side_effect = lambda k: {
            "g_client_id": "cid-value",
            "g_client_secret": "secret-value",
            "g_refresh_token": "token-value",
        }[k]
        backend = GoogleOAuthBackend(
            storage=storage,
            credential_name="google_drive",
            keys={
                "client_id": "g_client_id",
                "client_secret": "g_client_secret",
                "refresh_token": "g_refresh_token",
            },
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        creds = backend.get_credentials()

        assert isinstance(creds, Credentials)
        assert creds.client_id == "cid-value"
        assert creds.client_secret == "secret-value"
        assert creds.refresh_token == "token-value"
        assert creds.token is None  # auto-refreshed on first API call
        assert creds.token_uri == "https://oauth2.googleapis.com/token"
        assert creds.scopes == ["https://www.googleapis.com/auth/drive.file"]

    def test_get_credentials_raises_when_key_missing(self) -> None:
        from himitsubako.backends.google_oauth import GoogleOAuthBackend
        from himitsubako.errors import BackendError

        storage = MagicMock()
        storage.get.return_value = None  # all keys missing
        backend = GoogleOAuthBackend(
            storage=storage,
            credential_name="google_drive",
            keys={
                "client_id": "g_client_id",
                "client_secret": "g_client_secret",
                "refresh_token": "g_refresh_token",
            },
            scopes=["https://googleapis.com/auth/drive.file"],
        )
        with pytest.raises(BackendError, match="client_id"):
            backend.get_credentials()


class TestPythonApiGetGoogleCredentials:
    """AC-2: himitsubako.get_google_credentials() Python API."""

    def test_get_google_credentials_via_api(self, tmp_path: Path) -> None:
        """End-to-end: load config, resolve, get Credentials object."""
        from google.oauth2.credentials import Credentials

        # Build config pointing to a mock storage
        config_file = tmp_path / ".himitsubako.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "credentials": {
                        "google_drive": {
                            "backend": "google-oauth",
                            "storage_backend": "env",
                            "scopes": ["https://www.googleapis.com/auth/drive.file"],
                            "keys": {
                                "client_id": "GOOG_CID",
                                "client_secret": "GOOG_SECRET",
                                "refresh_token": "GOOG_TOKEN",
                            },
                        }
                    }
                }
            )
        )

        import os

        env = {"GOOG_CID": "cid-val", "GOOG_SECRET": "secret-val", "GOOG_TOKEN": "tok-val"}
        with patch.dict(os.environ, env), patch("himitsubako.api.Path.cwd", return_value=tmp_path):
            from himitsubako.api import get_google_credentials

            creds = get_google_credentials("google_drive")

        assert isinstance(creds, Credentials)
        assert creds.client_id == "cid-val"
        assert creds.refresh_token == "tok-val"

    def test_get_google_credentials_unknown_key_raises(self, tmp_path: Path) -> None:
        from himitsubako.errors import BackendError

        config_file = tmp_path / ".himitsubako.yaml"
        config_file.write_text(yaml.dump({}))

        with patch("himitsubako.api.Path.cwd", return_value=tmp_path):
            from himitsubako.api import get_google_credentials

            with pytest.raises(BackendError, match="not a google-oauth credential"):
                get_google_credentials("google_drive")


class TestCliGoogleOAuth:
    """AC-4 and AC-5: CLI integration for google-oauth credentials."""

    @staticmethod
    def _write_config(tmp_path: Path) -> None:
        (tmp_path / ".himitsubako.yaml").write_text(
            yaml.dump(
                {
                    "default_backend": "env",
                    "credentials": {
                        "google_drive": {
                            "backend": "google-oauth",
                            "storage_backend": "env",
                            "scopes": ["https://www.googleapis.com/auth/drive.file"],
                            "keys": {
                                "client_id": "GOOG_CID",
                                "client_secret": "GOOG_SECRET",
                                "refresh_token": "GOOG_TOKEN",
                            },
                        }
                    },
                }
            )
        )

    def test_cli_get_google_oauth_json_output(self, tmp_path: Path) -> None:
        """AC-4: `hmb get google_drive` emits JSON with all three fields."""
        import os

        from click.testing import CliRunner

        from himitsubako.cli import main

        self._write_config(tmp_path)
        runner = CliRunner()
        env = {
            "GOOG_CID": "cid-value",
            "GOOG_SECRET": "secret-value",
            "GOOG_TOKEN": "token-value",
        }
        with runner.isolated_filesystem(temp_dir=tmp_path):
            self._write_config(Path.cwd())
            with patch.dict(os.environ, env):
                # `--reveal` bypasses the TTY gate; CliRunner captures non-tty output.
                result = runner.invoke(main, ["get", "google_drive", "--reveal"])

        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output.strip())
        assert parsed == {
            "client_id": "cid-value",
            "client_secret": "secret-value",
            "refresh_token": "token-value",
        }

    def test_cli_set_google_oauth_interactive(self, tmp_path: Path) -> None:
        """AC-5: `hmb set google_drive` prompts for all three fields in order."""
        from click.testing import CliRunner

        from himitsubako.cli import main

        runner = CliRunner()
        captured_sets: list[tuple[str, str]] = []

        def fake_set(self, key: str, value: str) -> None:
            captured_sets.append((key, value))

        with runner.isolated_filesystem(temp_dir=tmp_path):
            self._write_config(Path.cwd())
            with patch("himitsubako.backends.env.EnvBackend.set", fake_set):
                result = runner.invoke(
                    main,
                    ["set", "google_drive"],
                    input="new-cid\nnew-secret\nnew-token\n",
                )

        assert result.exit_code == 0, result.output
        # EnvBackend.set should have been invoked for each of the three underlying keys.
        captured_keys = {k for k, _ in captured_sets}
        assert captured_keys == {"GOOG_CID", "GOOG_SECRET", "GOOG_TOKEN"}
        captured_values = dict(captured_sets)
        assert captured_values["GOOG_CID"] == "new-cid"
        assert captured_values["GOOG_SECRET"] == "new-secret"
        assert captured_values["GOOG_TOKEN"] == "new-token"


class TestIndividualKeyAccessUnchanged:
    """AC-6: individual key access through the storage backend still works."""

    def test_individual_keys_go_to_storage_backend(self, tmp_path: Path) -> None:
        """Exact match for a constituent key hits the storage backend directly."""
        import os

        config_file = tmp_path / ".himitsubako.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    # Default to env so the constituent key (which is not declared
                    # in credentials:) resolves via the env fallback.
                    "default_backend": "env",
                    "credentials": {
                        "google_drive": {
                            "backend": "google-oauth",
                            "storage_backend": "env",
                            "scopes": ["https://googleapis.com/auth/drive.file"],
                            "keys": {
                                "client_id": "GOOG_CID",
                                "client_secret": "GOOG_SECRET",
                                "refresh_token": "GOOG_TOKEN",
                            },
                        }
                    },
                }
            )
        )

        with (
            patch.dict(os.environ, {"GOOG_CID": "cid-value"}),
            patch("himitsubako.api.Path.cwd", return_value=tmp_path),
        ):
            from himitsubako.api import get

            assert get("GOOG_CID") == "cid-value"
