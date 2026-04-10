"""hmb get, hmb set, hmb list — core secret management commands."""

from __future__ import annotations

import sys

import click

from himitsubako.backends.sops import SopsBackend
from himitsubako.config import find_config, load_config
from himitsubako.errors import BackendError


def _resolve_backend() -> SopsBackend:
    """Resolve the backend from the nearest .himitsubako.yaml config."""
    from pathlib import Path as _Path

    config_path = find_config(_Path.cwd())
    if config_path is None:
        raise click.ClickException("no .himitsubako.yaml found (run 'hmb init' first)")

    config = load_config(config_path)
    project_dir = config_path.parent

    if config.default_backend == "sops":
        return SopsBackend(secrets_file=str(project_dir / config.sops.secrets_file))

    raise click.ClickException(f"backend '{config.default_backend}' not yet implemented")


@click.command("get")
@click.argument("key")
def get_secret(key: str) -> None:
    """Get a secret value by key."""
    try:
        backend = _resolve_backend()
        value = backend.get(key)
    except BackendError as exc:
        raise click.ClickException(str(exc)) from exc

    if value is None:
        click.echo(f"Secret '{key}' not found.", err=True)
        sys.exit(1)

    click.echo(value)


@click.command("set")
@click.argument("key")
@click.option("--value", default=None, help="Secret value (will prompt if omitted).")
def set_secret(key: str, value: str | None) -> None:
    """Set a secret value for a key."""
    if value is None:
        value = click.prompt("Value", hide_input=True)

    try:
        backend = _resolve_backend()
        backend.set(key, value)
    except BackendError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Set '{key}'.")


@click.command("list")
def list_secrets() -> None:
    """List all secret key names."""
    try:
        backend = _resolve_backend()
        keys = backend.list_keys()
    except BackendError as exc:
        raise click.ClickException(str(exc)) from exc

    if not keys:
        click.echo("No secrets found.")
        return

    for key in sorted(keys):
        click.echo(key)
