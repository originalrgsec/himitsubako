"""hmb init — scaffold a project for himitsubako."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import click
import yaml

from himitsubako.direnv import generate_envrc

_DEFAULT_KEYS_PATH = Path.home() / ".config" / "sops" / "age" / "keys.txt"
_SUBPROCESS_TIMEOUT = 30
_ENV_SOPS_BIN = "HIMITSUBAKO_SOPS_BIN"


def _resolve_sops_bin() -> str:
    """Resolve sops binary: env var > 'sops' on PATH (matches T-001)."""
    return os.environ.get(_ENV_SOPS_BIN, "").strip() or "sops"


def _ensure_age_key(keys_path: Path) -> str:
    """Return the age public key, creating a new keypair if needed.

    Reads the public key from the keys file comment line. If the file
    does not exist, generates a new keypair with age-keygen.
    """
    if keys_path.exists():
        for line in keys_path.read_text().splitlines():
            if line.startswith("# public key:"):
                return line.split(":", 1)[1].strip()
        msg = f"age keys file exists at {keys_path} but contains no public key comment"
        raise click.ClickException(msg)

    # Generate a new key
    keys_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            ["age-keygen"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise click.ClickException(
            "age-keygen not found on PATH. Install: https://github.com/FiloSottile/age"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise click.ClickException(f"age-keygen timed out after {_SUBPROCESS_TIMEOUT}s") from exc

    if result.returncode != 0:
        raise click.ClickException(f"age-keygen failed: {result.stderr}")

    # age-keygen prints "Public key: age1..." to stderr, writes secret key to stdout
    public_key = ""
    for line in result.stdout.splitlines():
        if line.startswith("Public key:"):
            public_key = line.split(":", 1)[1].strip()
            break

    if not public_key:
        # Some versions print to stderr
        for line in result.stderr.splitlines():
            if line.startswith("Public key:"):
                public_key = line.split(":", 1)[1].strip()
                break

    if not public_key:
        raise click.ClickException("age-keygen did not produce a public key")

    # Write the key file with the standard format
    keys_path.write_text(result.stdout)
    keys_path.chmod(0o600)

    return public_key


def _write_if_absent(path: Path, content: str, *, force: bool) -> bool:
    """Write content to path if it doesn't exist or force is True.

    Returns True if the file was written, False if skipped.
    """
    if path.exists() and not force:
        click.echo(f"  skip {path.name} (exists, use --force to overwrite)")
        return False
    path.write_text(content)
    click.echo(f"  wrote {path.name}")
    return True


def _build_sops_yaml(public_key: str) -> str:
    """Generate .sops.yaml content with the given age public key."""
    config = {
        "creation_rules": [
            {
                "path_regex": r"\.secrets\.enc\.yaml$",
                "age": public_key,
            }
        ]
    }
    return yaml.dump(config, default_flow_style=False)


def _build_envrc(secrets_file: str) -> str:
    """Generate .envrc content that sources decrypted secrets.

    Thin wrapper around himitsubako.direnv.generate_envrc — kept here so
    existing v0.1.0 tests that import _build_envrc continue to work
    while the canonical source moves into the direnv module.
    """
    return generate_envrc(secrets_file=secrets_file)


def _build_config_yaml() -> str:
    """Generate .himitsubako.yaml with sops as default backend."""
    config = {
        "default_backend": "sops",
        "sops": {
            "secrets_file": ".secrets.enc.yaml",
        },
    }
    return yaml.dump(config, default_flow_style=False)


@click.command()
@click.option("--force", is_flag=True, help="Overwrite existing files.")
def init(force: bool) -> None:
    """Initialize a project for himitsubako.

    Creates: age keypair (if needed), .sops.yaml, .envrc,
    .secrets.enc.yaml, and .himitsubako.yaml.
    """
    click.echo("Initializing himitsubako...")

    public_key = _ensure_age_key(_DEFAULT_KEYS_PATH)
    click.echo(f"  age public key: {public_key}")

    project_dir = Path.cwd()
    secrets_file = ".secrets.enc.yaml"

    _write_if_absent(project_dir / ".sops.yaml", _build_sops_yaml(public_key), force=force)
    _write_if_absent(project_dir / ".envrc", _build_envrc(secrets_file), force=force)
    _write_if_absent(project_dir / ".himitsubako.yaml", _build_config_yaml(), force=force)

    # Create empty encrypted secrets file
    secrets_path = project_dir / secrets_file
    if not secrets_path.exists() or force:
        # Write empty YAML, then encrypt with sops. Resolve the sops
        # binary via env var so HIMITSUBAKO_SOPS_BIN is honored here as
        # it is by SopsBackend (matches T-001 mitigation across all
        # call sites).
        sops_bin = _resolve_sops_bin()
        secrets_path.write_text(yaml.dump({}))
        try:
            result = subprocess.run(
                [sops_bin, "--encrypt", "--in-place", str(secrets_path)],
                capture_output=True,
                text=True,
                check=False,
                timeout=_SUBPROCESS_TIMEOUT,
            )
        except FileNotFoundError as exc:
            raise click.ClickException(
                f"sops binary not found at '{sops_bin}'. Install: https://github.com/getsops/sops"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise click.ClickException(
                f"sops encrypt timed out after {_SUBPROCESS_TIMEOUT}s"
            ) from exc

        if result.returncode != 0:
            click.echo(f"  warning: could not encrypt {secrets_file}: {result.stderr}")
        else:
            click.echo(f"  wrote {secrets_file} (encrypted)")
    else:
        click.echo(f"  skip {secrets_file} (exists, use --force to overwrite)")

    # Remind about .gitignore
    gitignore = project_dir / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if ".envrc" not in content:
            click.echo("  note: consider adding .envrc to .gitignore")
    else:
        click.echo("  note: no .gitignore found; consider creating one with .envrc entry")

    click.echo("Done.")
