"""HMB-S013: CLI end-to-end integration against real sops + age.

Exercises the full `hmb init → set → get → list → delete → list` flow
through Click's CliRunner against a real SOPS backend. Also covers
`hmb status` against found and not-found configurations.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from himitsubako.cli import main

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration


class TestCliFullFlow:
    def test_init_set_get_list_delete_flow(
        self,
        tmp_path: Path,
        age_keypair: tuple[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Drive a fresh project through init and the full CRUD cycle.

        We reuse the `age_keypair` fixture rather than letting `hmb init`
        run `age-keygen` so the test never touches the developer's real
        `~/.config/sops/age/keys.txt`. `_DEFAULT_KEYS_PATH` is
        monkeypatched to the fixture file so `_ensure_age_key` reads
        from it instead.
        """
        public_key, keys_file = age_keypair

        # Redirect hmb init's default keys path to the fixture key so it
        # cannot touch the real ~/.config/sops/age/keys.txt. The bare
        # name `himitsubako.cli.init` resolves to the Click Command (set
        # by the package __init__), so we grab the submodule explicitly.
        import importlib

        init_module = importlib.import_module("himitsubako.cli.init")
        monkeypatch.setattr(init_module, "_DEFAULT_KEYS_PATH", keys_file)
        monkeypatch.setenv("SOPS_AGE_KEY_FILE", str(keys_file))

        project = tmp_path / "e2e-project"
        project.mkdir()
        monkeypatch.chdir(project)

        runner = CliRunner()

        init_result = runner.invoke(main, ["init"])
        assert init_result.exit_code == 0, init_result.output
        assert public_key in init_result.output
        assert (project / ".himitsubako.yaml").exists()
        assert (project / ".sops.yaml").exists()
        assert (project / ".secrets.enc.yaml").exists()

        set_result = runner.invoke(main, ["set", "API_TOKEN", "--value", "tok-abc-123"])
        assert set_result.exit_code == 0, set_result.output

        set2_result = runner.invoke(main, ["set", "DB_PASS", "--value", "p@ss w/ spaces"])
        assert set2_result.exit_code == 0, set2_result.output

        # Pipe reads (is_tty = False under CliRunner) so --reveal is not
        # needed to print the value.
        get_result = runner.invoke(main, ["get", "API_TOKEN"])
        assert get_result.exit_code == 0, get_result.output
        assert "tok-abc-123" in get_result.output

        list_result = runner.invoke(main, ["list"])
        assert list_result.exit_code == 0, list_result.output
        assert "API_TOKEN" in list_result.output
        assert "DB_PASS" in list_result.output

        delete_result = runner.invoke(main, ["delete", "API_TOKEN", "--force"])
        assert delete_result.exit_code == 0, delete_result.output
        assert "deleted API_TOKEN" in delete_result.output

        list2_result = runner.invoke(main, ["list"])
        assert list2_result.exit_code == 0, list2_result.output
        assert "API_TOKEN" not in list2_result.output
        assert "DB_PASS" in list2_result.output

        gone_result = runner.invoke(main, ["get", "API_TOKEN"])
        assert gone_result.exit_code != 0

    def test_status_against_real_config(self, tmp_vault: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0, result.output
        assert ".himitsubako.yaml" in result.output
        assert "Default backend: sops" in result.output
        assert "sops: ok" in result.output

    def test_status_json_against_real_config(self, tmp_vault: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--json"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["default_backend"] == "sops"
        assert parsed["sops"]["binary"]
        assert parsed["backends"]["sops"]["status"] == "ok"

    def test_status_without_config_falls_back_to_env(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        empty = tmp_path / "no-config-dir"
        empty.mkdir()
        monkeypatch.chdir(empty)

        runner = CliRunner()
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0, result.output
        assert "not found" in result.output.lower()
        assert "env" in result.output
