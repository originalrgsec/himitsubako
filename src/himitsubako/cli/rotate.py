"""hmb rotate (credential value) and hmb rotate-key (age master key).

Two distinct commands, deliberately kept in the same module so the
distinction is visible at a glance:

- `hmb rotate <credential>` (HMB-S021) rotates the VALUE of a single
  credential by routing through BackendRouter, then writes one JSON
  Lines entry to `~/.himitsubako/audit.log`.
- `hmb rotate-key` (HMB-S005) re-encrypts the secrets file under a new
  age master key using `sops updatekeys`.
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
from pathlib import Path

import click
import yaml

from himitsubako.audit import write_audit_entry
from himitsubako.config import find_config, load_config
from himitsubako.errors import BackendError
from himitsubako.router import BackendRouter


def _stdin_is_tty() -> bool:
    """Indirection for testability — patched in tests to simulate TTY/pipe."""
    return sys.stdin.isatty()


def _read_public_key(keys_path: Path) -> str:
    """Extract the public key from an age keys file."""
    for line in keys_path.read_text().splitlines():
        if line.startswith("# public key:"):
            return line.split(":", 1)[1].strip()
    msg = f"no public key comment found in {keys_path}"
    raise click.ClickException(msg)


@click.command("rotate-key")
@click.option(
    "--new-key",
    required=True,
    type=click.Path(exists=False),
    help="Path to the new age keys file.",
)
@click.option("--dry-run", is_flag=True, help="Show what would change without modifying files.")
def rotate_key(new_key: str, dry_run: bool) -> None:
    """Re-encrypt secrets with a new age key."""
    new_key_path = Path(new_key)
    if not new_key_path.exists():
        raise click.ClickException(f"new key file not found: {new_key}")

    new_public_key = _read_public_key(new_key_path)

    # Find .sops.yaml and .himitsubako.yaml in cwd
    project_dir = Path.cwd()
    sops_yaml = project_dir / ".sops.yaml"
    config_yaml = project_dir / ".himitsubako.yaml"

    if not sops_yaml.exists():
        raise click.ClickException("no .sops.yaml found in current directory")

    # Load config to find secrets file
    secrets_file = ".secrets.enc.yaml"
    if config_yaml.exists():
        raw = yaml.safe_load(config_yaml.read_text())
        if isinstance(raw, dict):
            sops_config = raw.get("sops", {})
            if isinstance(sops_config, dict):
                secrets_file = sops_config.get("secrets_file", secrets_file)

    secrets_path = project_dir / secrets_file

    if dry_run:
        click.echo("Dry run — would perform the following:")
        click.echo(f"  Update .sops.yaml with new public key: {new_public_key}")
        if secrets_path.exists():
            click.echo(f"  Re-encrypt {secrets_file} with new key")
        else:
            click.echo(f"  Skip {secrets_file} (file does not exist)")
        return

    # Update .sops.yaml with new public key
    sops_config_data = yaml.safe_load(sops_yaml.read_text())
    if isinstance(sops_config_data, dict) and "creation_rules" in sops_config_data:
        for rule in sops_config_data["creation_rules"]:
            if isinstance(rule, dict) and "age" in rule:
                rule["age"] = new_public_key
    sops_yaml.write_text(yaml.dump(sops_config_data, default_flow_style=False))
    click.echo(f"  Updated .sops.yaml with new key: {new_public_key}")

    # Re-encrypt secrets file with sops
    if secrets_path.exists():
        try:
            result = subprocess.run(
                [
                    "sops",
                    "updatekeys",
                    "--yes",
                    str(secrets_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise click.ClickException(
                "sops not found on PATH. Install: https://github.com/getsops/sops"
            ) from exc

        if result.returncode != 0:
            raise click.ClickException(f"sops updatekeys failed: {result.stderr}")

        click.echo(f"  Re-encrypted {secrets_file}")
    else:
        click.echo(f"  Skip {secrets_file} (file does not exist)")

    click.echo("Key rotation complete.")


@click.command("rotate")
@click.argument("credential")
@click.option(
    "--value-from-file",
    default=None,
    type=click.Path(),
    help="Read the new value from a file instead of stdin.",
)
def rotate_credential(credential: str, value_from_file: str | None) -> None:
    """Rotate a credential's VALUE and append an audit log entry.

    Different from `hmb rotate-key`: this rotates one credential's value,
    while `hmb rotate-key` rotates the age master key. Reads the new
    value from stdin (pipe) by default; use --value-from-file to read
    from a file. Argv-based secret entry via --value is deliberately
    not supported.
    """
    # 1. Read the new value. TTY stdin is refused (secrets must not be
    #    typed interactively into the rotate flow — use hmb set for that).
    if value_from_file is not None:
        file_path = Path(value_from_file)
        if not file_path.exists():
            click.echo(f"Error: file not found: {value_from_file}", err=True)
            sys.exit(2)
        try:
            new_value = file_path.read_text().rstrip("\n")
        except OSError as exc:
            click.echo(f"Error: cannot read {value_from_file}: {exc}", err=True)
            sys.exit(2)
    else:
        if _stdin_is_tty():
            click.echo(
                "refusing to read a secret from a TTY. "
                "Pipe the new value on stdin, or use --value-from-file <path>.",
                err=True,
            )
            sys.exit(2)
        new_value = sys.stdin.read().rstrip("\n")

    # 2. Resolve the vault config and the target backend.
    config_path = find_config(Path.cwd())
    if config_path is None:
        raise click.ClickException("no .himitsubako.yaml found (run 'hmb init' first)")

    config = load_config(config_path)
    router = BackendRouter(config, project_dir=config_path.parent)
    try:
        target = router.resolve(credential)
    except BackendError as exc:
        click.echo(f"Error: {exc.detail}", err=True)
        sys.exit(1)

    backend_name = target.backend_name

    # 3. Perform the rotation. On failure, write a failure audit line
    #    (best-effort) and exit 1 without a warning if the audit write
    #    itself fails — the rotation failure is the primary signal.
    try:
        target.set(credential, new_value)
    except BackendError as exc:
        with contextlib.suppress(OSError):
            write_audit_entry(
                command="rotate",
                credential=credential,
                backend=backend_name,
                outcome="failure",
                vault_path=config_path,
                error=str(exc),
            )
        click.echo(f"Error: {exc.detail}", err=True)
        sys.exit(1)

    # 4. Rotation succeeded. Write the success audit line. If that fails,
    #    warn on stderr but do NOT roll back — a successful rotation with
    #    a missing audit line is less bad than an unwound rotation.
    try:
        write_audit_entry(
            command="rotate",
            credential=credential,
            backend=backend_name,
            outcome="success",
            vault_path=config_path,
        )
    except OSError as exc:
        click.echo(
            f"WARN: rotation succeeded but audit log write failed: {exc}",
            err=True,
        )

    click.echo(f"rotated {credential}")
