"""Tests for hmb get, hmb set, hmb list CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

from tests.conftest import write_env_config, write_sops_config


class TestHmbGet:
    """Test the hmb get command."""

    def test_get_existing_key_prints_value(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            decrypted = yaml.dump({"MY_KEY": "my_secret_value"})
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout=decrypted, stderr=""
                )
                result = runner.invoke(main, ["get", "MY_KEY"])

        assert result.exit_code == 0
        assert "my_secret_value" in result.output

    def test_get_missing_key_exits_nonzero(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            decrypted = yaml.dump({"OTHER": "val"})
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout=decrypted, stderr=""
                )
                result = runner.invoke(main, ["get", "NONEXISTENT"])

        assert result.exit_code != 0

    def test_get_no_key_argument_shows_usage(self):
        from himitsubako.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["get"])
        assert result.exit_code == 2


class TestGetRevealGate:
    """AC-4: hmb get --reveal TTY gate (T-018, ADR OQ-4)."""

    def _run_get(self, tmp_path, args, *, is_tty: bool):
        from himitsubako.cli import main
        from himitsubako.cli import secrets as secrets_module

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            decrypted = yaml.dump({"MY_KEY": "my_secret_value"})
            with (
                patch("subprocess.run") as mock_run,
                patch.object(
                    secrets_module, "_stdout_is_tty", return_value=is_tty
                ),
            ):
                mock_run.return_value = MagicMock(
                    returncode=0, stdout=decrypted, stderr=""
                )
                return runner.invoke(main, args)

    def test_pipe_without_reveal_prints_value(self, tmp_path):
        result = self._run_get(tmp_path, ["get", "MY_KEY"], is_tty=False)
        assert result.exit_code == 0
        assert "my_secret_value" in result.output

    def test_pipe_with_reveal_prints_value(self, tmp_path):
        result = self._run_get(
            tmp_path, ["get", "MY_KEY", "--reveal"], is_tty=False
        )
        assert result.exit_code == 0
        assert "my_secret_value" in result.output

    def test_tty_without_reveal_blocks_and_errors(self, tmp_path):
        result = self._run_get(tmp_path, ["get", "MY_KEY"], is_tty=True)
        assert result.exit_code != 0
        assert "my_secret_value" not in result.output
        assert "--reveal" in (result.output + (result.stderr or ""))

    def test_tty_with_reveal_prints_value(self, tmp_path):
        result = self._run_get(
            tmp_path, ["get", "MY_KEY", "--reveal"], is_tty=True
        )
        assert result.exit_code == 0
        assert "my_secret_value" in result.output

    def test_short_flag_r_works(self, tmp_path):
        result = self._run_get(tmp_path, ["get", "MY_KEY", "-r"], is_tty=True)
        assert result.exit_code == 0
        assert "my_secret_value" in result.output


class TestHmbSet:
    """Test the hmb set command."""

    def test_set_with_value_flag(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            decrypted = yaml.dump({})
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=decrypted, stderr=""),
                    MagicMock(returncode=0, stdout="", stderr=""),
                ]
                result = runner.invoke(
                    main, ["set", "NEW_KEY", "--value", "new_val"]
                )

        assert result.exit_code == 0

    def test_set_prompts_for_value(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            decrypted = yaml.dump({})
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=decrypted, stderr=""),
                    MagicMock(returncode=0, stdout="", stderr=""),
                ]
                result = runner.invoke(
                    main, ["set", "NEW_KEY"], input="prompted_val\n"
                )

        assert result.exit_code == 0


class TestHmbList:
    """Test the hmb list command."""

    def test_list_prints_key_names(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            decrypted = yaml.dump({"KEY_A": "a", "KEY_B": "b"})
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout=decrypted, stderr=""
                )
                result = runner.invoke(main, ["list"])

        assert result.exit_code == 0
        assert "KEY_A" in result.output
        assert "KEY_B" in result.output

    def test_list_empty_file(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            decrypted = yaml.dump({})
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout=decrypted, stderr=""
                )
                result = runner.invoke(main, ["list"])

        assert result.exit_code == 0


class TestEnvBackendDispatch:
    """HMB-S007: hmb get/set/list dispatch through EnvBackend when configured."""

    def test_get_with_env_backend_reads_environment(self, tmp_path, monkeypatch):
        from himitsubako.cli import main

        monkeypatch.setenv("HMB_ENV_TEST_KEY", "from_environment")
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_env_config(tmp_path)
            result = runner.invoke(main, ["get", "HMB_ENV_TEST_KEY", "--reveal"])

        assert result.exit_code == 0
        assert "from_environment" in result.output

    def test_get_with_env_backend_and_prefix(self, tmp_path, monkeypatch):
        import os

        from himitsubako.cli import main

        for k in [k for k in os.environ if k.startswith("MYAPP_")]:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("MYAPP_DB_PASSWORD", "prefixed_value")
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_env_config(tmp_path, prefix="MYAPP_")
            result = runner.invoke(main, ["get", "DB_PASSWORD", "--reveal"])

        assert result.exit_code == 0
        assert "prefixed_value" in result.output

    def test_get_missing_env_var_exits_nonzero(self, tmp_path, monkeypatch):
        from himitsubako.cli import main

        monkeypatch.delenv("DOES_NOT_EXIST_HMB", raising=False)
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_env_config(tmp_path)
            result = runner.invoke(main, ["get", "DOES_NOT_EXIST_HMB"])

        assert result.exit_code != 0

    def test_set_with_env_backend_errors_read_only(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_env_config(tmp_path)
            result = runner.invoke(main, ["set", "ANY", "--value", "v"])

        assert result.exit_code != 0
        assert "read-only" in (result.output + (result.stderr or ""))

    def test_list_with_env_backend_and_prefix_strips(
        self, tmp_path, monkeypatch
    ):
        import os

        from himitsubako.cli import main

        for k in [k for k in os.environ if k.startswith("MYAPP_")]:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("MYAPP_API_KEY", "x")
        monkeypatch.setenv("MYAPP_DB_PASSWORD", "y")
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_env_config(tmp_path, prefix="MYAPP_")
            result = runner.invoke(main, ["list"])

        assert result.exit_code == 0
        assert "API_KEY" in result.output
        assert "DB_PASSWORD" in result.output

    def test_list_with_env_backend_no_prefix_warns(self, tmp_path, monkeypatch):
        """Empty prefix triggers a stderr warning before listing."""
        from himitsubako.cli import main

        monkeypatch.setenv("HMB_WARN_PROBE", "1")
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_env_config(tmp_path, prefix="")
            result = runner.invoke(main, ["list"])

        assert result.exit_code == 0
        # Click 8.2+ keeps stderr separate by default; the warning lives there.
        assert "no prefix configured" in result.stderr
        # Probe variable still shows up because we are listing the full env.
        assert "HMB_WARN_PROBE" in result.stdout
