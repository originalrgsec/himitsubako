"""Tests for HMB-S039 — age private-key file mode race fix in hmb init.

HMB-S034 HIGH-3 / HMB-S039 AC-1: the age keys file must be created with
mode 0o600 atomically (no window exists where the file is wider than
0o600 between creation and mode-set).

HMB-S039 AC-2: on sops encrypt failure, init must unlink the plaintext
.secrets.enc.yaml and exit non-zero (was: warn-and-continue, leaving
a misleading artifact).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner


class TestAgeKeyFileModeAtomic:
    """HMB-S039 AC-1: age keys file mode is set atomically at creation."""

    def test_keys_file_created_with_mode_0600(self, tmp_path: Path) -> None:
        from himitsubako.cli.init import _ensure_age_key

        keys_file = tmp_path / "subdir" / "keys.txt"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=(
                    "# created: 2026-04-18\n# public key: age1newkey789\nAGE-SECRET-KEY-1FAKE\n"
                ),
                stderr="Public key: age1newkey789\n",
            )
            _ensure_age_key(keys_file)

        assert keys_file.exists()
        mode_bits = stat.S_IMODE(keys_file.stat().st_mode)
        assert mode_bits == 0o600, (
            f"keys file mode is {oct(mode_bits)}, expected 0o600 (HMB-S039 AC-1)"
        )

    def test_keys_file_uses_atomic_os_open_with_exclusive_create(self, tmp_path: Path) -> None:
        """Direct AC-1 proof: os.open called with O_CREAT|O_WRONLY|O_EXCL, 0o600.

        Proves the file is never wider than 0o600 during its lifetime.
        The mode argument to os.open is applied atomically with file
        creation (subject to umask narrowing, which can only remove bits).
        """
        from himitsubako.cli.init import _ensure_age_key

        keys_file = tmp_path / "subdir" / "keys.txt"
        real_os_open = os.open

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="# public key: age1atomickey\nAGE-SECRET-KEY-1FAKE\n",
                stderr="Public key: age1atomickey\n",
            )
            # Patch os.open at the init module's namespace so we see the
            # exact arguments the init code passes.
            with patch("himitsubako.cli.init.os.open", side_effect=real_os_open) as spy_open:
                _ensure_age_key(keys_file)

        # Find the call that opened the keys file for creation
        matching = [
            call
            for call in spy_open.call_args_list
            if call.args and str(call.args[0]).endswith("keys.txt")
        ]
        assert matching, (
            f"os.open was not invoked with the keys file path. calls: {spy_open.call_args_list}"
        )

        call = matching[0]
        flags = call.args[1]
        required = os.O_CREAT | os.O_WRONLY | os.O_EXCL
        assert flags & required == required, (
            f"os.open flags {flags:o} missing O_CREAT|O_WRONLY|O_EXCL"
        )
        mode_arg = call.args[2] if len(call.args) > 2 else call.kwargs.get("mode")
        assert mode_arg == 0o600, (
            f"os.open mode arg is {oct(mode_arg) if mode_arg is not None else None}, expected 0o600"
        )

    def test_keys_file_contains_age_keygen_stdout(self, tmp_path: Path) -> None:
        """Regression: the fix must still write the full age-keygen stdout."""
        from himitsubako.cli.init import _ensure_age_key

        keys_file = tmp_path / "subdir" / "keys.txt"
        expected_content = (
            "# created: 2026-04-18T00:00:00Z\n"
            "# public key: age1fullcontenttest\n"
            "AGE-SECRET-KEY-1FULLBODY\n"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=expected_content,
                stderr="Public key: age1fullcontenttest\n",
            )
            _ensure_age_key(keys_file)

        assert keys_file.read_text() == expected_content


class TestInitSopsEncryptFailure:
    """HMB-S039 AC-2: plaintext cleanup + non-zero exit on sops failure."""

    def test_init_exits_nonzero_when_sops_encrypt_fails(self, tmp_path: Path) -> None:
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            with patch("himitsubako.cli.init._ensure_age_key") as mock_age:
                mock_age.return_value = "age1testpublickey123"
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        returncode=1, stdout="", stderr="sops: no creation rule"
                    )
                    result = runner.invoke(main, ["init"])

            assert result.exit_code != 0, (
                f"expected non-zero exit on sops failure, got {result.exit_code} "
                f"(HMB-S039 AC-2). output:\n{result.output}"
            )
            assert "sops" in result.output.lower()

    def test_init_unlinks_plaintext_secrets_file_on_sops_failure(self, tmp_path: Path) -> None:
        from himitsubako.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            with patch("himitsubako.cli.init._ensure_age_key") as mock_age:
                mock_age.return_value = "age1testpublickey123"
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="sops: boom")
                    runner.invoke(main, ["init"])

            # Plaintext `{}` file must not be left behind.
            secrets_file = Path(td, ".secrets.enc.yaml")
            assert not secrets_file.exists(), (
                "plaintext .secrets.enc.yaml must be unlinked on sops failure (HMB-S039 AC-2)"
            )
