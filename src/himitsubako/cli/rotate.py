"""hmb rotate-key — re-encrypt secrets with a new age key."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click
import yaml


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
