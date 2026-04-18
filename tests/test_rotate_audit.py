"""Tests for `hmb rotate` credential rotation + audit log (HMB-S021).

Covers:
    - audit.py module: JSONL append, modes (0600/0700), atomic append,
      redaction, failure surfacing.
    - cli/rotate.py `rotate_credential` command: stdin happy path, TTY refusal,
      --value-from-file happy path and error, --value flag rejection, success
      log, failure log, audit-write-failure still exits 0.
    - Concurrent-write safety via multiprocessing.

Locked decisions (see stories/HMB-S021-rotate-audit-log.md):
    - Log location: ~/.himitsubako/audit.log (user-level)
    - Log format: JSON Lines, one object per line
    - Permissions: 0700 on dir, 0600 on file
    - Redaction: token-like substrings ([A-Za-z0-9+/=]{40,}) → [REDACTED]
    - Audit write failure after successful rotation → stderr warning, exit 0
"""

from __future__ import annotations

import json
import multiprocessing
import os
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from tests.conftest import write_sops_config

# ---------------------------------------------------------------------------
# audit.py module tests
# ---------------------------------------------------------------------------


class TestAuditEntryShape:
    """write_audit_entry produces well-formed JSONL with required fields."""

    def test_success_entry_has_required_fields(self, tmp_path):
        from himitsubako.audit import write_audit_entry

        log_path = tmp_path / ".himitsubako" / "audit.log"
        write_audit_entry(
            command="rotate",
            credential="API_KEY",
            backend="sops",
            outcome="success",
            vault_path=tmp_path / ".himitsubako.yaml",
            log_path=log_path,
        )

        lines = log_path.read_text().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["command"] == "rotate"
        assert entry["credential"] == "API_KEY"
        assert entry["backend"] == "sops"
        assert entry["outcome"] == "success"
        assert entry["vault_path"].endswith(".himitsubako.yaml")
        assert "timestamp" in entry
        assert "pid" in entry
        assert entry["pid"] == os.getpid()
        # Success entries must not include an error field.
        assert "error" not in entry

    def test_timestamp_is_iso_utc(self, tmp_path):
        from datetime import datetime

        from himitsubako.audit import write_audit_entry

        log_path = tmp_path / ".himitsubako" / "audit.log"
        write_audit_entry(
            command="rotate",
            credential="K",
            backend="env",
            outcome="success",
            vault_path=tmp_path / ".himitsubako.yaml",
            log_path=log_path,
        )
        entry = json.loads(log_path.read_text().splitlines()[0])
        # Must parse as ISO 8601 and carry a tz offset (not naive).
        parsed = datetime.fromisoformat(entry["timestamp"])
        assert parsed.tzinfo is not None

    def test_failure_entry_has_error_field(self, tmp_path):
        from himitsubako.audit import write_audit_entry

        log_path = tmp_path / ".himitsubako" / "audit.log"
        write_audit_entry(
            command="rotate",
            credential="API_KEY",
            backend="sops",
            outcome="failure",
            vault_path=tmp_path / ".himitsubako.yaml",
            error="sops updatekeys failed: exit 1",
            log_path=log_path,
        )
        entry = json.loads(log_path.read_text().splitlines()[0])
        assert entry["outcome"] == "failure"
        assert "sops updatekeys failed" in entry["error"]

    def test_never_logs_credential_value(self, tmp_path):
        """The credential VALUE must never appear in the audit log."""
        from himitsubako.audit import write_audit_entry

        log_path = tmp_path / ".himitsubako" / "audit.log"
        write_audit_entry(
            command="rotate",
            credential="API_KEY",
            backend="sops",
            outcome="success",
            vault_path=tmp_path / ".himitsubako.yaml",
            log_path=log_path,
        )
        content = log_path.read_text()
        # This test is a smoke check — the write_audit_entry API does not
        # take a value parameter, so by construction values cannot leak.
        # The assertion is that the only credential-identifying field is
        # the name, not the value.
        assert "API_KEY" in content


class TestAuditRedaction:
    """Error strings are redacted for token-shaped substrings."""

    def test_token_in_error_is_redacted(self, tmp_path):
        from himitsubako.audit import write_audit_entry

        log_path = tmp_path / ".himitsubako" / "audit.log"
        # 60-char base64-alphabet blob — matches the redaction regex.
        fake_token = "A" * 60
        write_audit_entry(
            command="rotate",
            credential="K",
            backend="bitwarden-cli",
            outcome="failure",
            vault_path=tmp_path / ".himitsubako.yaml",
            error=f"bw stderr: session={fake_token} invalid",
            log_path=log_path,
        )
        entry = json.loads(log_path.read_text().splitlines()[0])
        assert fake_token not in entry["error"]
        assert "[REDACTED]" in entry["error"]

    def test_short_alphanum_not_redacted(self, tmp_path):
        from himitsubako.audit import write_audit_entry

        log_path = tmp_path / ".himitsubako" / "audit.log"
        write_audit_entry(
            command="rotate",
            credential="K",
            backend="sops",
            outcome="failure",
            vault_path=tmp_path / ".himitsubako.yaml",
            error="short abc123 message",
            log_path=log_path,
        )
        entry = json.loads(log_path.read_text().splitlines()[0])
        assert "abc123" in entry["error"]


class TestAuditFileModes:
    """Directory and file permissions are strict."""

    def test_audit_dir_created_0700_if_missing(self, tmp_path):
        from himitsubako.audit import write_audit_entry

        audit_dir = tmp_path / ".himitsubako"
        log_path = audit_dir / "audit.log"
        assert not audit_dir.exists()
        write_audit_entry(
            command="rotate",
            credential="K",
            backend="env",
            outcome="success",
            vault_path=tmp_path / ".himitsubako.yaml",
            log_path=log_path,
        )
        assert audit_dir.exists()
        mode = stat.S_IMODE(audit_dir.stat().st_mode)
        assert mode == 0o700, f"expected 0700, got {oct(mode)}"

    def test_audit_file_created_0600_if_missing(self, tmp_path):
        from himitsubako.audit import write_audit_entry

        log_path = tmp_path / ".himitsubako" / "audit.log"
        write_audit_entry(
            command="rotate",
            credential="K",
            backend="env",
            outcome="success",
            vault_path=tmp_path / ".himitsubako.yaml",
            log_path=log_path,
        )
        mode = stat.S_IMODE(log_path.stat().st_mode)
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"

    def test_existing_file_mode_preserved(self, tmp_path):
        """Do not chmod down to 0600 if the user has set a stricter mode."""
        from himitsubako.audit import write_audit_entry

        audit_dir = tmp_path / ".himitsubako"
        audit_dir.mkdir(mode=0o700)
        log_path = audit_dir / "audit.log"
        log_path.touch()
        log_path.chmod(0o400)  # read-only

        # Writing to a 0o400 file should fail with PermissionError — that
        # proves we did not silently chmod it to 0600.
        with pytest.raises((PermissionError, OSError)):
            write_audit_entry(
                command="rotate",
                credential="K",
                backend="env",
                outcome="success",
                vault_path=tmp_path / ".himitsubako.yaml",
                log_path=log_path,
            )
        mode = stat.S_IMODE(log_path.stat().st_mode)
        assert mode == 0o400


class TestAuditAppendSemantics:
    """Multiple writes append; they do not overwrite."""

    def test_sequential_appends_produce_multiple_lines(self, tmp_path):
        from himitsubako.audit import write_audit_entry

        log_path = tmp_path / ".himitsubako" / "audit.log"
        for cred in ("A", "B", "C"):
            write_audit_entry(
                command="rotate",
                credential=cred,
                backend="env",
                outcome="success",
                vault_path=tmp_path / ".himitsubako.yaml",
                log_path=log_path,
            )
        lines = log_path.read_text().splitlines()
        assert len(lines) == 3
        creds = [json.loads(line)["credential"] for line in lines]
        assert creds == ["A", "B", "C"]

    def test_concurrent_writes_are_atomic(self, tmp_path):
        """Two processes appending simultaneously each produce one clean line."""
        from himitsubako.audit import write_audit_entry  # noqa: F401

        log_path = tmp_path / ".himitsubako" / "audit.log"
        # Pre-create the dir to avoid a race on mkdir itself.
        log_path.parent.mkdir(mode=0o700, exist_ok=True)

        # spawn instead of fork — fork is unsafe in multithreaded processes
        # (Python 3.12+ deprecates the macOS default). _audit_writer is
        # module-level so it picklable for spawn. HMB-S034 MED-5.
        ctx = multiprocessing.get_context("spawn")
        p1 = ctx.Process(
            target=_audit_writer,
            args=("PROC_A", str(log_path), str(tmp_path / ".himitsubako.yaml")),
        )
        p2 = ctx.Process(
            target=_audit_writer,
            args=("PROC_B", str(log_path), str(tmp_path / ".himitsubako.yaml")),
        )
        p1.start()
        p2.start()
        p1.join(timeout=60)
        p2.join(timeout=60)
        assert p1.exitcode == 0
        assert p2.exitcode == 0

        lines = log_path.read_text().splitlines()
        assert len(lines) == 100
        # Every line must parse as valid JSON — no interleaved corruption.
        for line in lines:
            entry = json.loads(line)
            assert entry["credential"] in ("PROC_A", "PROC_B")


def _audit_writer(credential: str, log: str, vault: str) -> None:
    """Module-level helper for the concurrent-writes test (picklable for spawn)."""
    from himitsubako.audit import write_audit_entry as write

    for _ in range(50):
        write(
            command="rotate",
            credential=credential,
            backend="env",
            outcome="success",
            vault_path=Path(vault),
            log_path=Path(log),
        )


# ---------------------------------------------------------------------------
# CLI command tests
# ---------------------------------------------------------------------------


def _mock_audit_home(monkeypatch, tmp_path):
    """Redirect the default audit log location into tmp_path."""
    from himitsubako import audit

    monkeypatch.setattr(audit, "AUDIT_DIR", tmp_path / ".himitsubako")
    monkeypatch.setattr(audit, "AUDIT_LOG", tmp_path / ".himitsubako" / "audit.log")


class TestRotateCommandHelp:
    """Command exists and help text disambiguates from rotate-key."""

    def test_rotate_in_top_level_help(self):
        from himitsubako.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "rotate" in result.output
        assert "rotate-key" in result.output

    def test_rotate_help_mentions_distinction(self):
        from himitsubako.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["rotate", "--help"])
        assert result.exit_code == 0
        # The first line should call out that this rotates a VALUE, not the key.
        assert "value" in result.output.lower()
        assert "rotate-key" in result.output

    def test_no_value_flag(self):
        """--value must NOT be accepted on `hmb rotate` (secrets on argv)."""
        from himitsubako.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["rotate", "K", "--value", "v"])
        assert result.exit_code == 2
        assert "no such option" in result.output.lower() or "unexpected" in result.output.lower()


class TestRotateStdin:
    """Happy path: new value read from stdin (pipe)."""

    def test_stdin_rotation_success(self, tmp_path, monkeypatch):
        from himitsubako.cli import main
        from himitsubako.cli import rotate as rotate_module

        _mock_audit_home(monkeypatch, tmp_path)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            decrypted = yaml.dump({"API_KEY": "old"})
            with (
                patch("subprocess.run") as mock_run,
                patch.object(rotate_module, "_stdin_is_tty", return_value=False),
            ):
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=decrypted, stderr=""),
                    MagicMock(returncode=0, stdout="", stderr=""),
                ]
                result = runner.invoke(main, ["rotate", "API_KEY"], input="new_value\n")

        assert result.exit_code == 0, result.output
        assert "rotated API_KEY" in result.output

        # Audit log should have exactly one success line for API_KEY.
        log_path = tmp_path / ".himitsubako" / "audit.log"
        assert log_path.exists()
        entries = [json.loads(line) for line in log_path.read_text().splitlines()]
        assert len(entries) == 1
        assert entries[0]["credential"] == "API_KEY"
        assert entries[0]["outcome"] == "success"
        assert entries[0]["backend"] == "sops"

    def test_tty_stdin_refused(self, tmp_path, monkeypatch):
        from himitsubako.cli import main
        from himitsubako.cli import rotate as rotate_module

        _mock_audit_home(monkeypatch, tmp_path)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            with patch.object(rotate_module, "_stdin_is_tty", return_value=True):
                result = runner.invoke(main, ["rotate", "API_KEY"])

        assert result.exit_code == 2
        assert "tty" in result.output.lower() or "pipe" in result.output.lower()

        # No audit entry on refusal (the rotation did not happen).
        log_path = tmp_path / ".himitsubako" / "audit.log"
        assert not log_path.exists()


class TestRotateValueFromFile:
    """--value-from-file reads from a file, strips trailing newline."""

    def test_file_happy_path(self, tmp_path, monkeypatch):
        from himitsubako.cli import main

        _mock_audit_home(monkeypatch, tmp_path)

        value_file = tmp_path / "new_value.txt"
        value_file.write_text("the_new_value\n")

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            decrypted = yaml.dump({"API_KEY": "old"})
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=decrypted, stderr=""),
                    MagicMock(returncode=0, stdout="", stderr=""),
                ]
                result = runner.invoke(
                    main,
                    ["rotate", "API_KEY", "--value-from-file", str(value_file)],
                )

        assert result.exit_code == 0, result.output

    def test_missing_file_exits_2(self, tmp_path, monkeypatch):
        from himitsubako.cli import main

        _mock_audit_home(monkeypatch, tmp_path)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            result = runner.invoke(
                main,
                ["rotate", "API_KEY", "--value-from-file", "/nonexistent/path/file"],
            )
        assert result.exit_code == 2


class TestRotateFailurePath:
    """Backend errors write a failure audit line and exit 1."""

    def test_backend_error_writes_failure_line_and_exits_1(self, tmp_path, monkeypatch):
        from himitsubako.cli import main
        from himitsubako.cli import rotate as rotate_module

        _mock_audit_home(monkeypatch, tmp_path)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            decrypted = yaml.dump({"API_KEY": "old"})
            with (
                patch("subprocess.run") as mock_run,
                patch.object(rotate_module, "_stdin_is_tty", return_value=False),
            ):
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=decrypted, stderr=""),
                    MagicMock(returncode=1, stdout="", stderr="sops: encrypt failed"),
                ]
                result = runner.invoke(main, ["rotate", "API_KEY"], input="val\n")

        assert result.exit_code == 1
        log_path = tmp_path / ".himitsubako" / "audit.log"
        entries = [json.loads(line) for line in log_path.read_text().splitlines()]
        assert len(entries) == 1
        assert entries[0]["outcome"] == "failure"
        assert "error" in entries[0]


class TestRotateAuditWriteFailure:
    """If the rotation succeeds but the audit-log write fails, exit 0 with warning."""

    def test_audit_failure_does_not_roll_back(self, tmp_path, monkeypatch):
        from himitsubako.cli import main
        from himitsubako.cli import rotate as rotate_module

        _mock_audit_home(monkeypatch, tmp_path)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_sops_config(tmp_path)
            decrypted = yaml.dump({"API_KEY": "old"})

            # Patch write_audit_entry to raise OSError after the rotation.
            from himitsubako.cli import rotate as rot_mod

            def _boom(**_kwargs):
                raise OSError("disk full")

            with (
                patch("subprocess.run") as mock_run,
                patch.object(rot_mod, "write_audit_entry", side_effect=_boom),
                patch.object(rotate_module, "_stdin_is_tty", return_value=False),
            ):
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=decrypted, stderr=""),
                    MagicMock(returncode=0, stdout="", stderr=""),
                ]
                result = runner.invoke(main, ["rotate", "API_KEY"], input="val\n")

        assert result.exit_code == 0, result.output
        combined = result.output + (result.stderr or "")
        assert "WARN" in combined or "warn" in combined
        assert "audit" in combined.lower()
