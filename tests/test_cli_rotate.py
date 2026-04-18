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
            "# created: 2026-04-10\n# public key: age1newpublickey456\nAGE-SECRET-KEY-1NEWKEYDATA\n"
        )

        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            write_sops_config(Path(td))
            (Path(td) / ".sops.yaml").write_text(yaml.dump(SOPS_CREATION_RULES))
            (Path(td) / ".secrets.enc.yaml").write_text("encrypted-content")

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                result = runner.invoke(main, ["rotate-key", "--new-key", str(new_key_file)])

        assert result.exit_code == 0

    def test_rotate_key_missing_new_key_file(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            result = runner.invoke(main, ["rotate-key", "--new-key", "/nonexistent/key.txt"])

        assert result.exit_code != 0

    def test_rotate_key_dry_run(self, tmp_path):
        from himitsubako.cli import main

        runner = CliRunner()
        new_key_file = tmp_path / "new_keys.txt"
        new_key_file.write_text(
            "# created: 2026-04-10\n# public key: age1newpublickey456\nAGE-SECRET-KEY-1NEWKEYDATA\n"
        )

        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            write_sops_config(Path(td))
            (Path(td) / ".sops.yaml").write_text(yaml.dump(SOPS_CREATION_RULES))
            (Path(td) / ".secrets.enc.yaml").write_text("encrypted-content")

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


class TestRotateKeySecurityHardening:
    """Regression coverage for HMB-S034 fixes (Sprint 8 /code-review)."""

    def test_rotate_key_honors_himitsubako_sops_bin_env(self, tmp_path, monkeypatch):
        """SEC-HIGH-2: rotate-key must use HIMITSUBAKO_SOPS_BIN, not bare 'sops'."""
        from himitsubako.cli import main

        monkeypatch.setenv("HIMITSUBAKO_SOPS_BIN", "/opt/custom/sops")

        runner = CliRunner()
        new_key_file = tmp_path / "new_keys.txt"
        new_key_file.write_text(
            "# created: 2026-04-10\n# public key: age1custompath\nAGE-SECRET-KEY-1XYZ\n"
        )

        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            write_sops_config(Path(td))
            (Path(td) / ".sops.yaml").write_text(yaml.dump(SOPS_CREATION_RULES))
            (Path(td) / ".secrets.enc.yaml").write_text("encrypted")

            captured_argv: list[list[str]] = []

            def fake_run(*args, **kwargs):
                argv = list(args[0]) if args else list(kwargs["args"])
                captured_argv.append(argv)
                return MagicMock(returncode=0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=fake_run):
                result = runner.invoke(main, ["rotate-key", "--new-key", str(new_key_file)])

        assert result.exit_code == 0, result.output
        # The configured custom path must appear as the binary, not bare "sops".
        assert any(call[0] == "/opt/custom/sops" for call in captured_argv), captured_argv

    def test_read_rotation_value_strips_crlf_from_file(self, tmp_path):
        """LOW-1/SEC-LOW-1: rstrip should drop \\r\\n, not just \\n."""
        from himitsubako.cli.rotate import _read_rotation_value

        # Windows-style line ending — would silently store the \r before fix.
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("my-secret-value\r\n")

        result = _read_rotation_value(str(secret_file))
        assert result == "my-secret-value"
        assert not result.endswith("\r")

    def test_rotate_key_atomic_write_of_sops_yaml(self, tmp_path):
        """HIGH-1: .sops.yaml must be written atomically (tempfile + replace)."""
        from himitsubako.cli import main

        runner = CliRunner()
        new_key_file = tmp_path / "new_keys.txt"
        new_key_file.write_text(
            "# created: 2026-04-10\n# public key: age1atomic\nAGE-SECRET-KEY-1ATOMIC\n"
        )

        # Simulate disk-full / process-kill mid-write by making os.fdopen raise
        # AFTER the tempfile has been created. We expect the original
        # .sops.yaml to be UNCHANGED (atomic invariant).
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            sops_yaml = Path(td) / ".sops.yaml"
            original_content = yaml.dump(SOPS_CREATION_RULES, default_flow_style=False)
            sops_yaml.write_text(original_content)
            (Path(td) / ".secrets.enc.yaml").write_text("encrypted")

            real_fdopen = __import__("os").fdopen

            def boom(*args, **kwargs):
                # First call (the atomic write) blows up; subsequent calls
                # (e.g., subprocess pipes) pass through.
                if not boom.fired:
                    boom.fired = True
                    raise OSError("simulated disk full")
                return real_fdopen(*args, **kwargs)

            boom.fired = False

            with (
                patch("subprocess.run") as mock_run,
                patch("os.fdopen", side_effect=boom),
            ):
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                result = runner.invoke(main, ["rotate-key", "--new-key", str(new_key_file)])

            # The simulated failure must abort the rotation, not silently pass.
            assert result.exit_code != 0
            # The original .sops.yaml must be intact — atomicity invariant.
            assert sops_yaml.read_text() == original_content
