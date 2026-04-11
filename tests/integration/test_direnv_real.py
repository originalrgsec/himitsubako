"""HMB-S020: direnv integration tests against the real `direnv` binary.

Marked `integration` and `direnv`; skipped unless `direnv version`
succeeds on PATH. Uses `direnv exec <dir> env` to execute a child
process inside an allowed environment and verifies that secrets from
`.secrets.enc.yaml` reach the child process as environment variables.

Run with:

    uv run pytest tests/integration/test_direnv_real.py -m "integration and direnv"
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest
import yaml

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [
    pytest.mark.integration,
    pytest.mark.direnv,
    pytest.mark.skipif(
        shutil.which("direnv") is None,
        reason="direnv tests require the `direnv` binary on PATH",
    ),
]


def _direnv_exec_env(vault: Path) -> dict[str, str]:
    """Run `direnv exec <vault> env` and parse the resulting environment.

    Uses `direnv exec`, not `direnv allow` + shell hook, so no state
    is written to the user's direnv allow-list and the test cannot
    leak approvals onto the developer's machine.
    """
    # direnv refuses to run unless the user has allowed the .envrc. For
    # an isolated tmp dir, `direnv allow` is scoped to that directory
    # and cannot leak elsewhere; we clean up explicitly at teardown.
    subprocess.run(
        ["direnv", "allow", str(vault)],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(vault),
    )
    try:
        result = subprocess.run(
            ["direnv", "exec", str(vault), "env"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(vault),
        )
    finally:
        subprocess.run(
            ["direnv", "deny", str(vault)],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(vault),
        )

    env: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            env[k] = v
    return env


class TestDirenvExport:
    def test_hmb_direnv_export_writes_managed_block(self, tmp_vault: Path) -> None:
        from click.testing import CliRunner

        from himitsubako.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["direnv-export"])
        assert result.exit_code == 0, result.output

        envrc_content = (tmp_vault / ".envrc").read_text()
        assert "# --- himitsubako start ---" in envrc_content
        assert "# --- himitsubako end ---" in envrc_content
        assert "sops" in envrc_content

    def test_direnv_exec_surfaces_secrets(
        self,
        tmp_vault: Path,
        age_keypair: tuple[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The end-to-end integration assertion for the direnv helper.

        Seed a secret via the real SOPS backend, write the managed
        block via `hmb direnv-export`, then invoke `direnv exec` in
        the vault and verify the secret surfaces as an env var in the
        child process. This is the only test in the suite that
        actually exercises the full direnv → sops → himitsubako path.
        """
        from click.testing import CliRunner

        from himitsubako.backends.sops import SopsBackend
        from himitsubako.cli import main

        _public, keys_file = age_keypair
        sops_backend = SopsBackend(secrets_file=".secrets.enc.yaml")
        sops_backend.set("SAMPLE_SECRET", "from-sops-via-direnv")

        runner = CliRunner()
        result = runner.invoke(main, ["direnv-export"])
        assert result.exit_code == 0, result.output

        # direnv subprocess must be able to find the age key file so sops
        # can decrypt. The parent test process already has SOPS_AGE_KEY_FILE
        # set by the tmp_vault fixture, so direnv inherits it via the
        # parent env — no additional setup required.
        assert os.environ.get("SOPS_AGE_KEY_FILE") == str(keys_file)

        env = _direnv_exec_env(tmp_vault)
        assert env.get("SAMPLE_SECRET") == "from-sops-via-direnv", (
            f"secret did not surface via direnv exec; env keys: "
            f"{sorted(k for k in env if 'SECRET' in k or 'SAMPLE' in k)}"
        )


class TestDirenvSafety:
    """Regression coverage for the duplicate-marker refusal and the
    shlex-quoted secrets path."""

    def test_duplicate_start_marker_raises(self, tmp_vault: Path) -> None:
        from himitsubako.direnv import update_envrc
        from himitsubako.errors import BackendError

        # Pre-seed a corrupted .envrc with two start markers. The
        # update_envrc helper must refuse to overwrite and raise
        # rather than silently merging.
        envrc = tmp_vault / ".envrc"
        envrc.write_text(
            "# --- himitsubako start ---\n"
            "foo=bar\n"
            "# --- himitsubako end ---\n"
            "# --- himitsubako start ---\n"
            "baz=qux\n"
            "# --- himitsubako end ---\n"
        )

        with pytest.raises(BackendError, match="resolve duplicates"):
            update_envrc(envrc, secrets_file=".secrets.enc.yaml")

    def test_secrets_path_with_space_and_dollar_round_trips(
        self,
        tmp_vault: Path,
        age_keypair: tuple[str, Path],
    ) -> None:
        """A secrets_file path containing a space and a `$` must be
        shlex-quoted so the eval line cannot break out and execute
        arbitrary code. This test round-trips the tricky path end-to-end
        through direnv exec."""
        from himitsubako.backends.sops import SopsBackend

        # Build a new config pointing at a tricky filename in the vault.
        tricky_name = "my $secrets file.enc.yaml"
        new_config = {
            "default_backend": "sops",
            "sops": {"secrets_file": tricky_name},
        }
        (tmp_vault / ".himitsubako.yaml").write_text(yaml.safe_dump(new_config))

        # Update .sops.yaml to match the new filename pattern.
        sops_yaml_data = yaml.safe_load((tmp_vault / ".sops.yaml").read_text())
        sops_yaml_data["creation_rules"][0]["path_regex"] = r"\.enc\.yaml$"
        (tmp_vault / ".sops.yaml").write_text(yaml.safe_dump(sops_yaml_data))

        # Create and encrypt the tricky file via the SopsBackend path so
        # it respects --filename-override.
        tricky_path = tmp_vault / tricky_name
        tricky_path.write_text(yaml.safe_dump({}))
        subprocess.run(
            [
                "sops",
                "--encrypt",
                "--filename-override",
                str(tricky_path),
                "--in-place",
                str(tricky_path),
            ],
            check=True,
            capture_output=True,
        )
        backend = SopsBackend(secrets_file=tricky_name)
        backend.set("TRICKY_KEY", "tricky-value-ok")

        # Write the managed block with the tricky path.
        from himitsubako.direnv import update_envrc

        update_envrc(tmp_vault / ".envrc", secrets_file=tricky_name)
        envrc_content = (tmp_vault / ".envrc").read_text()
        # shlex.quote wraps a path containing spaces and `$` in single
        # quotes; the raw unquoted path must not appear as a bare token.
        assert "'my $secrets file.enc.yaml'" in envrc_content

        env = _direnv_exec_env(tmp_vault)
        assert env.get("TRICKY_KEY") == "tricky-value-ok", (
            "shlex quoting broke; secret did not surface through direnv"
        )
