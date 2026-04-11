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


class TestHmbDelete:
    """HMB-S018: hmb delete CLI command."""

    def _run_sops_delete(
        self,
        tmp_path,
        args,
        *,
        existing: dict[str, str],
        input_text: str | None = None,
    ):
        """Run hmb delete against a SOPS-backed config with `existing` secrets.

        The mock supplies enough decrypt/encrypt responses for any round-trip
        the command may perform.
        """
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            decrypted = yaml.dump(existing)
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=decrypted, stderr=""),
                    MagicMock(returncode=0, stdout="", stderr=""),
                    MagicMock(returncode=0, stdout=decrypted, stderr=""),
                    MagicMock(returncode=0, stdout="", stderr=""),
                ]
                return runner.invoke(main, args, input=input_text)

    def test_force_deletes_existing_key(self, tmp_path):
        result = self._run_sops_delete(
            tmp_path,
            ["delete", "MY_KEY", "--force"],
            existing={"MY_KEY": "v", "OTHER": "o"},
        )
        assert result.exit_code == 0, result.output
        assert "deleted MY_KEY" in result.output

    def test_yes_alias_equivalent_to_force(self, tmp_path):
        result = self._run_sops_delete(
            tmp_path,
            ["delete", "MY_KEY", "--yes"],
            existing={"MY_KEY": "v"},
        )
        assert result.exit_code == 0, result.output
        assert "deleted MY_KEY" in result.output

    def test_prompt_accept_y_deletes(self, tmp_path):
        result = self._run_sops_delete(
            tmp_path,
            ["delete", "MY_KEY"],
            existing={"MY_KEY": "v"},
            input_text="y\n",
        )
        assert result.exit_code == 0, result.output
        assert "deleted MY_KEY" in result.output
        assert "sops" in result.output

    def test_prompt_reject_aborts_without_delete(self, tmp_path):
        result = self._run_sops_delete(
            tmp_path,
            ["delete", "MY_KEY"],
            existing={"MY_KEY": "v"},
            input_text="n\n",
        )
        assert result.exit_code == 0
        assert "deleted MY_KEY" not in result.output

    def test_prompt_empty_input_aborts(self, tmp_path):
        result = self._run_sops_delete(
            tmp_path,
            ["delete", "MY_KEY"],
            existing={"MY_KEY": "v"},
            input_text="\n",
        )
        assert result.exit_code == 0
        assert "deleted MY_KEY" not in result.output

    def test_missing_key_without_missing_ok_exits_1(self, tmp_path):
        result = self._run_sops_delete(
            tmp_path,
            ["delete", "NOPE", "--force"],
            existing={"OTHER": "v"},
        )
        assert result.exit_code == 1
        stderr = result.stderr or result.output
        assert "not found" in stderr

    def test_missing_key_with_missing_ok_exits_0_silent(self, tmp_path):
        result = self._run_sops_delete(
            tmp_path,
            ["delete", "NOPE", "--force", "--missing-ok"],
            existing={"OTHER": "v"},
        )
        assert result.exit_code == 0
        assert "deleted" not in result.output
        assert "not found" not in (result.output + (result.stderr or ""))

    def test_missing_ok_with_interactive_prompt_confirmed(self, tmp_path):
        """Cover confirmed-prompt + absent-key + --missing-ok path."""
        result = self._run_sops_delete(
            tmp_path,
            ["delete", "NOPE", "--missing-ok"],
            existing={"OTHER": "v"},
            input_text="y\n",
        )
        assert result.exit_code == 0
        assert "deleted" not in result.output
        assert "not found" not in (result.output + (result.stderr or ""))

    def test_env_backend_read_only_exits_2(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_env_config(tmp_path)
            result = runner.invoke(main, ["delete", "ANY", "--force"])

        assert result.exit_code == 2, result.output
        stderr = result.stderr or result.output
        assert "read-only" in stderr

    def test_routed_dispatch_prompt_names_resolved_backend(
        self, tmp_path, monkeypatch
    ):
        """BackendRouter: prompt must show the target backend_name, not 'router'."""
        from himitsubako.cli import main

        monkeypatch.setenv("HMB_ROUTED_KEY", "from_env")
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            config = {
                "default_backend": "sops",
                "sops": {"secrets_file": ".secrets.enc.yaml"},
                "env": {"prefix": "HMB_"},
                "credentials": {
                    "ROUTED_KEY": {"backend": "env"},
                },
            }
            (tmp_path / ".himitsubako.yaml").write_text(yaml.dump(config))
            result = runner.invoke(main, ["delete", "ROUTED_KEY"], input="n\n")

        assert "env" in result.output
        assert "deleted ROUTED_KEY" not in result.output

    def test_routed_dispatch_force_hits_target_backend(
        self, tmp_path, monkeypatch
    ):
        """With --force and an env-routed key, dispatch must raise backend error."""
        from himitsubako.cli import main

        monkeypatch.setenv("HMB_ROUTED_KEY", "x")
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            config = {
                "default_backend": "sops",
                "sops": {"secrets_file": ".secrets.enc.yaml"},
                "env": {"prefix": "HMB_"},
                "credentials": {"ROUTED_KEY": {"backend": "env"}},
            }
            (tmp_path / ".himitsubako.yaml").write_text(yaml.dump(config))
            result = runner.invoke(
                main, ["delete", "ROUTED_KEY", "--force"]
            )

        assert result.exit_code == 2
        assert "read-only" in (result.output + (result.stderr or ""))
