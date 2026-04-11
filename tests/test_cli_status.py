"""Tests for hmb status (HMB-S019)."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

from tests.conftest import write_env_config, write_sops_config


def _write_sops_yaml(tmp_path, recipient: str = "age1testrecipient") -> None:
    (tmp_path / ".sops.yaml").write_text(
        yaml.dump(
            {
                "creation_rules": [
                    {"path_regex": r"\.secrets\.enc\.yaml$", "age": recipient},
                ]
            }
        )
    )


class TestStatusConfigFound:
    """Config loaded successfully — human output path."""

    def test_sops_config_prints_binary_and_recipient(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            _write_sops_yaml(tmp_path, recipient="age1exampleabc")
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="sops 3.8.1\n", stderr=""
                )
                result = runner.invoke(main, ["status"])

        assert result.exit_code == 0, result.output
        assert "Config:" in result.output
        assert ".himitsubako.yaml" in result.output
        assert "Default backend: sops" in result.output
        assert "SOPS:" in result.output
        assert "age1exampleabc" in result.output
        assert "sops: ok" in result.output

    def test_env_config_prints_default_backend_env(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_env_config(tmp_path, prefix="MYAPP_")
            result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "Default backend: env" in result.output
        assert "env: ok" in result.output


class TestStatusConfigNotFound:
    """No .himitsubako.yaml found — should report and fall back."""

    def test_prints_not_found_and_exits_zero(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "not found" in result.output.lower()
        # Fallback to env backend view.
        assert "env" in result.output


class TestStatusRouter:
    """BackendRouter: patterns listed in config order."""

    def test_router_patterns_in_order(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            config = {
                "default_backend": "sops",
                "sops": {"secrets_file": ".secrets.enc.yaml"},
                "env": {"prefix": "MYAPP_"},
                "credentials": {
                    "ZETA_KEY": {"backend": "sops"},
                    "ALPHA_KEY": {"backend": "env"},
                    "BETA_*": {"backend": "env"},
                },
            }
            # sort_keys=False to preserve declared order in YAML output.
            (tmp_path / ".himitsubako.yaml").write_text(
                yaml.dump(config, sort_keys=False)
            )
            _write_sops_yaml(tmp_path)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="sops 3.8.1\n", stderr=""
                )
                result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        out = result.output
        assert "Router:" in out
        zeta = out.index("ZETA_KEY")
        alpha = out.index("ALPHA_KEY")
        beta = out.index("BETA_*")
        assert zeta < alpha < beta, "router rows must appear in config order"


class TestStatusJson:
    """--json output is valid JSON and contains expected keys."""

    def test_json_output_schema(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            _write_sops_yaml(tmp_path)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="sops 3.8.1\n", stderr=""
                )
                result = runner.invoke(main, ["status", "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "config_path" in parsed
        assert parsed["default_backend"] == "sops"
        assert "sops" in parsed
        assert parsed["sops"]["binary"]
        assert "router" in parsed
        assert "backends" in parsed
        assert parsed["backends"]["sops"]["status"] == "ok"

    def test_json_output_config_not_found(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["status", "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["config_path"] is None
        assert parsed["default_backend"] == "env"


class TestStatusSopsUnavailable:
    """Backend unavailability is reported, exit code stays 0."""

    def test_sops_binary_missing(self, tmp_path, monkeypatch):
        from himitsubako.cli import main

        monkeypatch.setenv("HIMITSUBAKO_SOPS_BIN", "/nonexistent/sops")
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            _write_sops_yaml(tmp_path)
            result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "sops: unavailable" in result.output
        assert "/nonexistent/sops" in result.output


class TestStatusSecretSafety:
    """Regression: status must never print any secret value."""

    def test_seeded_secret_absent_from_output(self, tmp_path):
        from himitsubako.cli import main

        secret_value = "HYPER_SECRET_VALUE_DO_NOT_LEAK_1234567890"
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            _write_sops_yaml(tmp_path)
            # Seed an encrypted secrets file with plaintext-looking content;
            # status must not decrypt anything.
            (tmp_path / ".secrets.enc.yaml").write_text(
                yaml.dump({"MY_SECRET": secret_value})
            )
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="sops 3.8.1\n", stderr=""
                )
                result = runner.invoke(main, ["status", "--json"])
                result2 = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert result2.exit_code == 0
        assert secret_value not in result.output
        assert secret_value not in result2.output


class TestStatusBackendChecks:
    """Exercise the per-backend availability check branches."""

    def test_sops_returncode_nonzero_marks_unavailable(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            _write_sops_yaml(tmp_path)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1, stdout="", stderr="boom"
                )
                result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "sops: unavailable" in result.output
        assert "exit 1" in result.output

    def test_sops_timeout_marks_unavailable(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            _write_sops_yaml(tmp_path)
            with patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="sops", timeout=5),
            ):
                result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "sops: unavailable" in result.output
        assert "timed out" in result.output

    def test_sops_oserror_marks_unavailable(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            _write_sops_yaml(tmp_path)
            with patch("subprocess.run", side_effect=OSError("permission denied")):
                result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "sops: unavailable" in result.output
        assert "invoke failed" in result.output

    def test_keychain_unavailable_when_resolve_raises(self, tmp_path):
        from himitsubako.backends.keychain import KeychainBackend
        from himitsubako.cli import main
        from himitsubako.errors import BackendError

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            (tmp_path / ".himitsubako.yaml").write_text(
                yaml.dump(
                    {
                        "default_backend": "keychain",
                        "keychain": {"service": "himitsubako"},
                    }
                )
            )
            with patch.object(
                KeychainBackend,
                "check_availability",
                side_effect=BackendError("keychain", "insecure backend detected"),
            ):
                result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "keychain: unavailable" in result.output
        assert "insecure backend detected" in result.output

    def test_keychain_ok_when_resolve_succeeds(self, tmp_path):
        from himitsubako.backends.keychain import KeychainBackend
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            (tmp_path / ".himitsubako.yaml").write_text(
                yaml.dump(
                    {
                        "default_backend": "keychain",
                        "keychain": {"service": "himitsubako"},
                    }
                )
            )
            with patch.object(
                KeychainBackend, "check_availability", return_value=None
            ):
                result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "keychain: ok" in result.output

    def test_keychain_unexpected_exception_caught(self, tmp_path):
        """Review regression: a non-BackendError (e.g. broken plugin init) must
        be surfaced as 'unavailable' with exit 0, not crash the command."""
        from himitsubako.backends.keychain import KeychainBackend
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            (tmp_path / ".himitsubako.yaml").write_text(
                yaml.dump(
                    {
                        "default_backend": "keychain",
                        "keychain": {"service": "custom-svc"},
                    }
                )
            )
            with patch.object(
                KeychainBackend,
                "check_availability",
                side_effect=RuntimeError("plugin init blew up"),
            ):
                result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "keychain: unavailable" in result.output
        assert "plugin init blew up" in result.output

    def test_keychain_instantiated_with_configured_service(self, tmp_path):
        """Review regression: the availability probe must use the configured
        `service`, not the default — otherwise the check probes a different
        keychain namespace than the one the user configured."""
        from himitsubako.cli import main

        seen_services: list[str] = []

        class _StubBackend:
            def __init__(self, service: str = "himitsubako") -> None:
                seen_services.append(service)

            def check_availability(self) -> None:
                return None

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            (tmp_path / ".himitsubako.yaml").write_text(
                yaml.dump(
                    {
                        "default_backend": "keychain",
                        "keychain": {"service": "my-custom-service"},
                    }
                )
            )
            with patch(
                "himitsubako.backends.keychain.KeychainBackend", _StubBackend
            ):
                result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "my-custom-service" in seen_services

    def test_bitwarden_nonzero_exit_with_json_body_is_unavailable(self, tmp_path):
        """Review regression: non-zero exit code from `bw status` must force
        'unavailable' even when stdout still parses as JSON with a status field."""
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            (tmp_path / ".himitsubako.yaml").write_text(
                yaml.dump(
                    {
                        "default_backend": "bitwarden-cli",
                        "bitwarden": {"folder": "himitsubako"},
                    }
                )
            )
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1,
                    stdout='{"status": "unauthenticated"}',
                    stderr="",
                )
                result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "bitwarden-cli: unavailable" in result.output
        assert "exit 1" in result.output

    def test_bitwarden_unavailable_binary_missing(self, tmp_path, monkeypatch):
        from himitsubako.cli import main

        monkeypatch.setenv("HIMITSUBAKO_BW_BIN", "/nonexistent/bw")
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            (tmp_path / ".himitsubako.yaml").write_text(
                yaml.dump(
                    {
                        "default_backend": "bitwarden-cli",
                        "bitwarden": {"folder": "himitsubako"},
                    }
                )
            )
            result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "bitwarden-cli: unavailable" in result.output
        assert "/nonexistent/bw" in result.output

    def test_bitwarden_ok_with_lock_state(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            (tmp_path / ".himitsubako.yaml").write_text(
                yaml.dump(
                    {
                        "default_backend": "bitwarden-cli",
                        "bitwarden": {"folder": "himitsubako"},
                    }
                )
            )
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout='{"status": "locked"}',
                    stderr="",
                )
                result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "bitwarden-cli: ok" in result.output
        assert "vault locked" in result.output

    def test_bitwarden_nonzero_exit_marks_unavailable(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            (tmp_path / ".himitsubako.yaml").write_text(
                yaml.dump(
                    {
                        "default_backend": "bitwarden-cli",
                        "bitwarden": {"folder": "himitsubako"},
                    }
                )
            )
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=2, stdout="", stderr="boom"
                )
                result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "bitwarden-cli: unavailable" in result.output


class TestStatusSopsRecipientsParse:
    """_read_sops_recipients branches."""

    def test_missing_sops_yaml_yields_empty_recipients(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            # No .sops.yaml at all.
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="sops 3.8.1\n", stderr=""
                )
                result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "recipients: <none" in result.output

    def test_malformed_sops_yaml_yields_empty_recipients(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            (tmp_path / ".sops.yaml").write_text("!!!!! not yaml ::::")
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="sops 3.8.1\n", stderr=""
                )
                result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "recipients: <none" in result.output


class TestStatusMalformedConfig:
    """ConfigError path: malformed YAML exits non-zero."""

    def test_malformed_config_exits_nonzero(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            (tmp_path / ".himitsubako.yaml").write_text(
                "default_backend: sops\n  bad: [unclosed\n"
            )
            result = runner.invoke(main, ["status"])

        assert result.exit_code != 0
