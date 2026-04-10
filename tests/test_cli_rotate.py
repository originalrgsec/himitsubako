"""Tests for hmb rotate-key CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

from tests.conftest import SOPS_CREATION_RULES, write_sops_config


class TestHmbRotateKey:
    """Test the hmb rotate-key command."""

    def test_rotate_key_command_exists(self):
        from himitsubako.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["rotate-key", "--help"])
        assert result.exit_code == 0
        assert "rotate" in result.output.lower()

    def test_rotate_key_with_new_key(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        new_key_file = tmp_path / "new_keys.txt"
        new_key_file.write_text(
            "# created: 2026-04-10\n"
            "# public key: age1newpublickey456\n"
            "AGE-SECRET-KEY-1NEWKEYDATA\n"
        )

        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            write_sops_config(Path(td))
            (Path(td) / ".sops.yaml").write_text(
                yaml.dump(SOPS_CREATION_RULES)
            )
            (Path(td) / ".secrets.enc.yaml").write_text(
                "encrypted-content"
            )

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="", stderr=""
                )
                result = runner.invoke(
                    main, ["rotate-key", "--new-key", str(new_key_file)]
                )

        assert result.exit_code == 0

    def test_rotate_key_missing_new_key_file(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            result = runner.invoke(
                main, ["rotate-key", "--new-key", "/nonexistent/key.txt"]
            )

        assert result.exit_code != 0

    def test_rotate_key_dry_run(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        new_key_file = tmp_path / "new_keys.txt"
        new_key_file.write_text(
            "# created: 2026-04-10\n"
            "# public key: age1newpublickey456\n"
            "AGE-SECRET-KEY-1NEWKEYDATA\n"
        )

        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            write_sops_config(Path(td))
            (Path(td) / ".sops.yaml").write_text(
                yaml.dump(SOPS_CREATION_RULES)
            )
            (Path(td) / ".secrets.enc.yaml").write_text(
                "encrypted-content"
            )

            with patch("subprocess.run") as mock_run:
                result = runner.invoke(
                    main,
                    ["rotate-key", "--new-key", str(new_key_file), "--dry-run"],
                )

            # Dry run should not call sops
            mock_run.assert_not_called()

        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "dry run" in output_lower or "would" in output_lower
