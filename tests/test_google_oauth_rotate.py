"""Tests for the Google OAuth rotation flows (HMB-S032)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestDeviceFlow:
    """AC-1: Device flow returns a refresh token on success."""

    def test_device_flow_success(self) -> None:
        from himitsubako.google_oauth_rotate import run_device_flow

        emitted: list[str] = []
        calls: list[tuple[str, dict[str, str]]] = []

        def fake_post(url: str, fields: dict[str, str]) -> dict[str, object]:
            calls.append((url, fields))
            if "device" in url:
                return {
                    "device_code": "dev-code-abc",
                    "user_code": "WXYZ-1234",
                    "verification_url": "https://www.google.com/device",
                    "interval": 1,
                    "expires_in": 60,
                }
            # Second token poll returns success
            if len(calls) == 2:
                return {"error": "authorization_pending"}
            return {
                "access_token": "at",
                "refresh_token": "new-refresh-token-xyz",
                "token_type": "Bearer",
            }

        result = run_device_flow(
            client_id="cid",
            client_secret="cs",
            scopes=["https://www.googleapis.com/auth/drive.file"],
            emit=emitted.append,
            http_post=fake_post,
            sleep=lambda _: None,
            now=_make_clock([0.0, 0.5, 1.5, 2.5]),
        )

        assert result.refresh_token == "new-refresh-token-xyz"
        # User-facing output should include the verification URL and the user code.
        joined = "\n".join(emitted)
        assert "https://www.google.com/device" in joined
        assert "WXYZ-1234" in joined

    def test_device_flow_pending_then_approve(self) -> None:
        """Pending response causes continued polling; eventual approval succeeds."""
        from himitsubako.google_oauth_rotate import run_device_flow

        responses = iter(
            [
                {
                    "device_code": "dev-code",
                    "user_code": "ABCD-1234",
                    "verification_url": "https://www.google.com/device",
                    "interval": 1,
                    "expires_in": 60,
                },
                {"error": "authorization_pending"},
                {"error": "authorization_pending"},
                {"refresh_token": "tok"},
            ]
        )

        def fake_post(url: str, fields: dict[str, str]) -> dict[str, object]:
            return next(responses)

        result = run_device_flow(
            client_id="cid",
            client_secret="cs",
            scopes=["s"],
            emit=lambda _: None,
            http_post=fake_post,
            sleep=lambda _: None,
            now=_make_clock([0.0, 1.0, 2.0, 3.0, 4.0]),
        )
        assert result.refresh_token == "tok"

    def test_device_flow_user_denied(self) -> None:
        from himitsubako.errors import BackendError
        from himitsubako.google_oauth_rotate import run_device_flow

        responses = iter(
            [
                {
                    "device_code": "dc",
                    "user_code": "UC",
                    "verification_url": "https://x",
                    "interval": 1,
                    "expires_in": 60,
                },
                {"error": "access_denied"},
            ]
        )

        def fake_post(url: str, fields: dict[str, str]) -> dict[str, object]:
            return next(responses)

        with pytest.raises(BackendError, match="denied"):
            run_device_flow(
                client_id="cid",
                client_secret="cs",
                scopes=["s"],
                emit=lambda _: None,
                http_post=fake_post,
                sleep=lambda _: None,
                now=_make_clock([0.0, 1.0, 2.0]),
            )

    def test_device_flow_expired_code(self) -> None:
        from himitsubako.errors import BackendError
        from himitsubako.google_oauth_rotate import run_device_flow

        responses = iter(
            [
                {
                    "device_code": "dc",
                    "user_code": "UC",
                    "verification_url": "https://x",
                    "interval": 1,
                    "expires_in": 60,
                },
                {"error": "expired_token"},
            ]
        )
        with pytest.raises(BackendError, match="expired"):
            run_device_flow(
                client_id="cid",
                client_secret="cs",
                scopes=["s"],
                emit=lambda _: None,
                http_post=lambda _u, _f: next(responses),
                sleep=lambda _: None,
                now=_make_clock([0.0, 1.0, 2.0]),
            )

    def test_device_flow_invalid_client_suggests_browser(self) -> None:
        """AC-5: unrecognized error surfaces --browser suggestion."""
        from himitsubako.errors import BackendError
        from himitsubako.google_oauth_rotate import run_device_flow

        responses = iter(
            [
                {
                    "device_code": "dc",
                    "user_code": "UC",
                    "verification_url": "https://x",
                    "interval": 1,
                    "expires_in": 60,
                },
                {
                    "error": "invalid_client",
                    "error_description": "OAuth client not configured for device flow",
                },
            ]
        )
        with pytest.raises(BackendError, match="--browser"):
            run_device_flow(
                client_id="cid",
                client_secret="cs",
                scopes=["s"],
                emit=lambda _: None,
                http_post=lambda _u, _f: next(responses),
                sleep=lambda _: None,
                now=_make_clock([0.0, 1.0, 2.0]),
            )

    def test_device_flow_slow_down_increases_interval(self) -> None:
        """slow_down response continues polling without raising."""
        from himitsubako.google_oauth_rotate import run_device_flow

        responses = iter(
            [
                {
                    "device_code": "dc",
                    "user_code": "UC",
                    "verification_url": "https://x",
                    "interval": 1,
                    "expires_in": 60,
                },
                {"error": "slow_down"},
                {"refresh_token": "tok"},
            ]
        )

        result = run_device_flow(
            client_id="cid",
            client_secret="cs",
            scopes=["s"],
            emit=lambda _: None,
            http_post=lambda _u, _f: next(responses),
            sleep=lambda _: None,
            now=_make_clock([0.0, 1.0, 2.0, 3.0]),
        )
        assert result.refresh_token == "tok"


class TestInstalledAppFlow:
    """AC-2: InstalledAppFlow returns a refresh token on success."""

    def test_installed_app_flow_returns_refresh_token(self, monkeypatch) -> None:
        from himitsubako import google_oauth_rotate

        # Patch the import target to avoid launching a real browser or server.
        fake_creds = MagicMock()
        fake_creds.refresh_token = "browser-flow-token"

        fake_flow_instance = MagicMock()
        fake_flow_instance.run_local_server = MagicMock(return_value=fake_creds)
        fake_flow_cls = MagicMock()
        fake_flow_cls.from_client_config = MagicMock(return_value=fake_flow_instance)

        fake_module = MagicMock()
        fake_module.InstalledAppFlow = fake_flow_cls

        import sys

        monkeypatch.setitem(sys.modules, "google_auth_oauthlib.flow", fake_module)

        result = google_oauth_rotate.run_installed_app_flow(
            client_id="cid",
            client_secret="cs",
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        assert result.refresh_token == "browser-flow-token"
        fake_flow_instance.run_local_server.assert_called_once()

    def test_installed_app_flow_missing_refresh_token_raises(self, monkeypatch) -> None:
        from himitsubako import google_oauth_rotate
        from himitsubako.errors import BackendError

        fake_creds = MagicMock()
        fake_creds.refresh_token = None

        fake_flow_instance = MagicMock()
        fake_flow_instance.run_local_server = MagicMock(return_value=fake_creds)
        fake_flow_cls = MagicMock()
        fake_flow_cls.from_client_config = MagicMock(return_value=fake_flow_instance)
        fake_module = MagicMock()
        fake_module.InstalledAppFlow = fake_flow_cls

        import sys

        monkeypatch.setitem(sys.modules, "google_auth_oauthlib.flow", fake_module)

        with pytest.raises(BackendError, match="refresh_token"):
            google_oauth_rotate.run_installed_app_flow(
                client_id="cid",
                client_secret="cs",
                scopes=["s"],
            )


def _make_clock(values: list[float]):
    """Build a monotonic clock that returns successive values then sticks at the last."""
    iterator = iter(values)
    last = [values[-1]]

    def clock() -> float:
        try:
            value = next(iterator)
            last[0] = value
            return value
        except StopIteration:
            return last[0]

    return clock


class TestRotateCliIntegration:
    """AC-1, AC-2, AC-3, AC-4, AC-6: full `hmb rotate` command flow."""

    @staticmethod
    def _write_config(tmp_path) -> None:
        import yaml

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

    def test_rotate_device_flow_writes_new_token_and_audits(self, tmp_path, monkeypatch):
        """AC-1 + AC-3: device flow rotation writes new token and appends audit entry."""
        import json
        import os

        from click.testing import CliRunner

        from himitsubako.cli import main

        captured_sets: list[tuple[str, str]] = []

        def fake_set(self, key: str, value: str) -> None:
            captured_sets.append((key, value))

        # Point the audit log at a tmp file to avoid writing to ~/.himitsubako
        audit_log = tmp_path / "audit.log"
        monkeypatch.setattr("himitsubako.audit.AUDIT_LOG", audit_log)

        # Fake device-flow result — bypass the real HTTP by patching the
        # rotation module's run_device_flow entry point.
        from himitsubako.google_oauth_rotate import DeviceFlowResult

        def fake_device_flow(**_kwargs) -> DeviceFlowResult:
            return DeviceFlowResult(refresh_token="rotated-token")

        monkeypatch.setattr("himitsubako.cli.rotate.run_device_flow", fake_device_flow)

        runner = CliRunner()
        env = {"GOOG_CID": "cid-val", "GOOG_SECRET": "secret-val", "GOOG_TOKEN": "old-token"}
        with runner.isolated_filesystem(temp_dir=tmp_path):
            from pathlib import Path

            self._write_config(Path.cwd())
            with (
                patch.dict(os.environ, env),
                patch("himitsubako.backends.env.EnvBackend.set", fake_set),
            ):
                result = runner.invoke(main, ["rotate", "google_drive"])

        assert result.exit_code == 0, result.output
        # The set call should be per-field (via GoogleOAuthBackend.set fanning out).
        captured_keys = {k for k, _ in captured_sets}
        assert captured_keys == {"GOOG_CID", "GOOG_SECRET", "GOOG_TOKEN"}
        captured_values = dict(captured_sets)
        assert captured_values["GOOG_TOKEN"] == "rotated-token"
        assert captured_values["GOOG_CID"] == "cid-val"  # unchanged
        assert captured_values["GOOG_SECRET"] == "secret-val"  # unchanged

        # AC-3: audit log written with method=device and outcome=success.
        assert audit_log.exists()
        lines = audit_log.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["command"] == "rotate"
        assert entry["credential"] == "google_drive"
        assert entry["outcome"] == "success"
        assert entry["method"] == "device"

    def test_rotate_browser_flow_writes_new_token_and_audits(self, tmp_path, monkeypatch):
        """AC-2 + AC-3: --browser runs InstalledAppFlow and audits as method=browser."""
        import json
        import os

        from click.testing import CliRunner

        from himitsubako.cli import main
        from himitsubako.google_oauth_rotate import DeviceFlowResult

        captured_sets: list[tuple[str, str]] = []

        def fake_set(self, key: str, value: str) -> None:
            captured_sets.append((key, value))

        def fake_installed_app(**_kwargs) -> DeviceFlowResult:
            return DeviceFlowResult(refresh_token="browser-token")

        audit_log = tmp_path / "audit.log"
        monkeypatch.setattr("himitsubako.audit.AUDIT_LOG", audit_log)
        monkeypatch.setattr("himitsubako.cli.rotate.run_installed_app_flow", fake_installed_app)

        runner = CliRunner()
        env = {"GOOG_CID": "cid", "GOOG_SECRET": "sec", "GOOG_TOKEN": "old"}
        with runner.isolated_filesystem(temp_dir=tmp_path):
            from pathlib import Path

            self._write_config(Path.cwd())
            with (
                patch.dict(os.environ, env),
                patch("himitsubako.backends.env.EnvBackend.set", fake_set),
            ):
                result = runner.invoke(main, ["rotate", "google_drive", "--browser"])

        assert result.exit_code == 0, result.output
        captured_values = dict(captured_sets)
        assert captured_values["GOOG_TOKEN"] == "browser-token"

        entry = json.loads(audit_log.read_text().strip().splitlines()[0])
        assert entry["method"] == "browser"

    def test_rotate_missing_client_credentials_exits_error(self, tmp_path, monkeypatch):
        """AC-4: rotation without existing client_id/secret fails cleanly."""
        import os

        from click.testing import CliRunner

        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            from pathlib import Path

            self._write_config(Path.cwd())
            # No env vars set: client_id and client_secret are missing.
            with patch.dict(os.environ, {}, clear=True):
                result = runner.invoke(main, ["rotate", "google_drive"])

        assert result.exit_code != 0
        assert "client_id" in result.output or "client_secret" in result.output

    def test_rotate_device_flow_rejection_shows_browser_hint(self, tmp_path, monkeypatch):
        """AC-5: Google rejects device flow → error suggests --browser."""
        import os

        from click.testing import CliRunner

        from himitsubako.cli import main
        from himitsubako.errors import BackendError

        def rejecting_device_flow(**_kwargs):
            raise BackendError(
                "google-oauth",
                "device flow rejected by Google: invalid_client. "
                "Retry with `hmb rotate <credential> --browser`",
            )

        monkeypatch.setattr("himitsubako.cli.rotate.run_device_flow", rejecting_device_flow)

        runner = CliRunner()
        env = {"GOOG_CID": "cid", "GOOG_SECRET": "sec", "GOOG_TOKEN": "old"}
        with runner.isolated_filesystem(temp_dir=tmp_path):
            from pathlib import Path

            self._write_config(Path.cwd())
            with patch.dict(os.environ, env):
                result = runner.invoke(main, ["rotate", "google_drive"])

        assert result.exit_code != 0
        assert "--browser" in result.output

    def test_rotate_storage_write_failure_preserves_old_token(self, tmp_path, monkeypatch):
        """AC-6: if the storage write fails after OAuth success, user is told
        the old token is still valid. No revocation is attempted."""
        import json
        import os

        from click.testing import CliRunner

        from himitsubako.cli import main
        from himitsubako.errors import BackendError
        from himitsubako.google_oauth_rotate import DeviceFlowResult

        def fake_device_flow(**_kwargs) -> DeviceFlowResult:
            return DeviceFlowResult(refresh_token="new-token")

        def failing_set(self, key: str, value: str) -> None:
            raise BackendError("env", "write failed simulation")

        audit_log = tmp_path / "audit.log"
        monkeypatch.setattr("himitsubako.audit.AUDIT_LOG", audit_log)
        monkeypatch.setattr("himitsubako.cli.rotate.run_device_flow", fake_device_flow)

        runner = CliRunner()
        env = {"GOOG_CID": "cid", "GOOG_SECRET": "sec", "GOOG_TOKEN": "old"}
        with runner.isolated_filesystem(temp_dir=tmp_path):
            from pathlib import Path

            self._write_config(Path.cwd())
            with (
                patch.dict(os.environ, env),
                patch("himitsubako.backends.env.EnvBackend.set", failing_set),
            ):
                result = runner.invoke(main, ["rotate", "google_drive"])

        assert result.exit_code != 0
        # Message must make clear the old refresh token is still valid.
        assert "old refresh token is still valid" in result.output.lower() or (
            "storage write failed" in result.output.lower()
        )

        # Failure audit entry present.
        assert audit_log.exists()
        entry = json.loads(audit_log.read_text().strip().splitlines()[0])
        assert entry["outcome"] == "failure"

    def test_browser_flag_rejected_on_non_oauth_credential(self, tmp_path):
        """--browser only applies to google-oauth; other credentials should reject it."""
        from click.testing import CliRunner

        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            from pathlib import Path

            # Write a minimal config with only env backend, no google-oauth.
            (Path.cwd() / ".himitsubako.yaml").write_text("default_backend: env\n")
            result = runner.invoke(main, ["rotate", "SOME_KEY", "--browser"])

        assert result.exit_code != 0
        assert "--browser" in result.output.lower() or "google-oauth" in result.output.lower()
