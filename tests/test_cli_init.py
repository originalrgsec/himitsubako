"""Tests for the hmb init CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner


class TestHmbInit:
    """Test the hmb init command."""

    def test_cli_entry_point_exists(self):
        from himitsubako.cli import main

        assert main is not None

    def test_init_creates_config_file(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            with patch("himitsubako.cli.init._ensure_age_key") as mock_age:
                mock_age.return_value = "age1testpublickey123"
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                    result = runner.invoke(main, ["init"])

            assert result.exit_code == 0, result.output
            assert Path(td, ".himitsubako.yaml").exists()

    def test_init_creates_sops_yaml(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            with patch("himitsubako.cli.init._ensure_age_key") as mock_age:
                mock_age.return_value = "age1testpublickey123"
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                    runner.invoke(main, ["init"])

            sops_yaml = Path(td, ".sops.yaml")
            assert sops_yaml.exists()
            config = yaml.safe_load(sops_yaml.read_text())
            assert "creation_rules" in config

    def test_init_creates_envrc(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            with patch("himitsubako.cli.init._ensure_age_key") as mock_age:
                mock_age.return_value = "age1testpublickey123"
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                    runner.invoke(main, ["init"])

            envrc = Path(td, ".envrc")
            assert envrc.exists()
            content = envrc.read_text()
            assert "sops" in content

    def test_init_does_not_overwrite_without_force(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            # Pre-create the config
            Path(td, ".himitsubako.yaml").write_text("existing: true\n")

            with patch("himitsubako.cli.init._ensure_age_key") as mock_age:
                mock_age.return_value = "age1testpublickey123"
                # Mock sops so the encrypt path succeeds — HMB-S039
                # made init exit non-zero on sops failure, so we must
                # not trigger that here.
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                    result = runner.invoke(main, ["init"])

            assert result.exit_code == 0
            # Original content preserved
            content = Path(td, ".himitsubako.yaml").read_text()
            assert "existing" in content

    def test_init_overwrites_with_force(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            Path(td, ".himitsubako.yaml").write_text("existing: true\n")

            with patch("himitsubako.cli.init._ensure_age_key") as mock_age:
                mock_age.return_value = "age1testpublickey123"
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                    result = runner.invoke(main, ["init", "--force"])

            assert result.exit_code == 0
            content = Path(td, ".himitsubako.yaml").read_text()
            assert "existing" not in content


class TestEnsureAgeKey:
    """Test age key creation/detection logic."""

    def test_returns_public_key_when_exists(self, tmp_path):
        from himitsubako.cli.init import _ensure_age_key

        keys_file = tmp_path / "keys.txt"
        keys_file.write_text(
            "# created: 2026-04-10\n# public key: age1abc123def456\nAGE-SECRET-KEY-1FAKEKEYDATA\n"
        )
        result = _ensure_age_key(keys_file)
        assert result == "age1abc123def456"

    def test_creates_key_when_missing(self, tmp_path):
        from himitsubako.cli.init import _ensure_age_key

        keys_file = tmp_path / "subdir" / "keys.txt"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Public key: age1newkey789\n",
                stderr="",
            )
            result = _ensure_age_key(keys_file)

        assert result == "age1newkey789"
        mock_run.assert_called_once()
