"""HMB-S013: SOPS backend integration tests against real sops + age.

Exercises the shipped SopsBackend via its public API with real binaries.
See `conftest.py` for the `tmp_vault` / `age_keypair` fixtures.
"""

from __future__ import annotations

import stat
import subprocess
from typing import TYPE_CHECKING

import pytest
import yaml

if TYPE_CHECKING:
    from pathlib import Path

from himitsubako.backends.sops import SopsBackend
from himitsubako.errors import SecretNotFoundError

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helper assertions


def _assert_mode_0600(path: Path) -> None:
    """Enforce the T-010 regression: secrets file must be mode 0600."""
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600, (
        f"{path.name} mode is {oct(mode)}; T-010 requires 0o600"
    )


# ---------------------------------------------------------------------------
# Round-trip with tricky values


class TestSopsRoundTrip:
    def test_set_get_simple_key(self, tmp_vault: Path) -> None:
        backend = SopsBackend(secrets_file=".secrets.enc.yaml")
        backend.set("SIMPLE", "hello-world")
        assert backend.get("SIMPLE") == "hello-world"
        _assert_mode_0600(tmp_vault / ".secrets.enc.yaml")

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("SHORT_ASCII", "abc123"),
            (
                "NEWLINE_VALUE",
                "line1\nline2\nline3",
            ),
            (
                "DOLLAR_AND_BACKTICK",
                "literal $var and `backtick` and \"quotes\"",
            ),
            (
                "LONG_RANDOMISH",
                "A" * 1024 + "Z" * 512,
            ),
            (
                "UTF8_NON_ASCII",
                "パスワード-🔐-rätsel",
            ),
        ],
    )
    def test_varied_charsets_round_trip(
        self, tmp_vault: Path, key: str, value: str
    ) -> None:
        backend = SopsBackend(secrets_file=".secrets.enc.yaml")
        backend.set(key, value)
        assert backend.get(key) == value
        _assert_mode_0600(tmp_vault / ".secrets.enc.yaml")

    def test_multiple_keys_coexist(self, tmp_vault: Path) -> None:
        backend = SopsBackend(secrets_file=".secrets.enc.yaml")
        payload = {
            "KEY_ONE": "value-one",
            "KEY_TWO": "value-two",
            "KEY_THREE": "value-three",
        }
        for k, v in payload.items():
            backend.set(k, v)
        for k, v in payload.items():
            assert backend.get(k) == v


class TestSopsListAndDelete:
    def test_list_returns_set_keys(self, tmp_vault: Path) -> None:
        backend = SopsBackend(secrets_file=".secrets.enc.yaml")
        for k in ("ALPHA", "BETA", "GAMMA"):
            backend.set(k, f"v-{k}")
        keys = sorted(backend.list_keys())
        assert keys == ["ALPHA", "BETA", "GAMMA"]

    def test_delete_removes_key(self, tmp_vault: Path) -> None:
        backend = SopsBackend(secrets_file=".secrets.enc.yaml")
        backend.set("TO_DELETE", "disposable")
        backend.set("KEEP_ME", "survivor")
        backend.delete("TO_DELETE")
        assert backend.get("TO_DELETE") is None
        assert backend.get("KEEP_ME") == "survivor"
        assert "TO_DELETE" not in backend.list_keys()
        _assert_mode_0600(tmp_vault / ".secrets.enc.yaml")

    def test_delete_missing_key_raises_not_found(self, tmp_vault: Path) -> None:
        backend = SopsBackend(secrets_file=".secrets.enc.yaml")
        with pytest.raises(SecretNotFoundError):
            backend.delete("NEVER_SET")


class TestSopsFileModeGuard:
    """T-010 regression: mode 0600 on both initial write and update."""

    def test_mode_after_first_set(self, tmp_vault: Path) -> None:
        backend = SopsBackend(secrets_file=".secrets.enc.yaml")
        backend.set("FIRST", "one")
        _assert_mode_0600(tmp_vault / ".secrets.enc.yaml")

    def test_mode_after_overwrite(self, tmp_vault: Path) -> None:
        backend = SopsBackend(secrets_file=".secrets.enc.yaml")
        backend.set("FIRST", "one")
        (tmp_vault / ".secrets.enc.yaml").chmod(0o644)
        backend.set("SECOND", "two")
        _assert_mode_0600(tmp_vault / ".secrets.enc.yaml")


class TestSopsRotateKey:
    """`hmb rotate-key` end-to-end via CLI against real sops updatekeys."""

    def test_rotate_swaps_recipient_and_old_key_cannot_decrypt(
        self,
        tmp_vault: Path,
        age_keypair: tuple[str, Path],
        second_age_keypair: tuple[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from click.testing import CliRunner

        from himitsubako.cli import main

        old_public, old_keys_file = age_keypair
        new_public, new_keys_file = second_age_keypair

        # Seed a secret before rotation.
        backend = SopsBackend(secrets_file=".secrets.enc.yaml")
        backend.set("PRE_ROTATE", "pre-value")
        assert backend.get("PRE_ROTATE") == "pre-value"

        # Rotate: give sops access to BOTH keys so updatekeys can decrypt
        # the current file (with old_keys) and re-encrypt it to new_public.
        combined = tmp_vault / "combined-keys.txt"
        combined.write_text(
            old_keys_file.read_text() + "\n" + new_keys_file.read_text()
        )
        combined.chmod(0o600)
        monkeypatch.setenv("SOPS_AGE_KEY_FILE", str(combined))

        runner = CliRunner()
        result = runner.invoke(
            main, ["rotate-key", "--new-key", str(new_keys_file)]
        )
        assert result.exit_code == 0, result.output
        assert "Key rotation complete." in result.output

        # .sops.yaml now names the new recipient.
        sops_yaml = yaml.safe_load((tmp_vault / ".sops.yaml").read_text())
        recipients = [
            rule["age"]
            for rule in sops_yaml["creation_rules"]
            if "age" in rule
        ]
        assert new_public in recipients
        assert old_public not in recipients

        # New key can still read the pre-rotate secret.
        monkeypatch.setenv("SOPS_AGE_KEY_FILE", str(new_keys_file))
        backend_new = SopsBackend(secrets_file=".secrets.enc.yaml")
        assert backend_new.get("PRE_ROTATE") == "pre-value"

        # Old key alone can no longer decrypt — sops returns non-zero.
        monkeypatch.setenv("SOPS_AGE_KEY_FILE", str(old_keys_file))
        result_dec = subprocess.run(
            ["sops", "--decrypt", str(tmp_vault / ".secrets.enc.yaml")],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result_dec.returncode != 0, (
            "old age key should no longer decrypt the rotated secrets file; "
            f"sops output: {result_dec.stdout}"
        )
