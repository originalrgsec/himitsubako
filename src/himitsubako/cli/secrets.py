"""hmb get, hmb set, hmb list — core secret management commands."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import click

from himitsubako.backends.env import EnvBackend
from himitsubako.config import find_config, load_config
from himitsubako.errors import BackendError
from himitsubako.router import BackendRouter

if TYPE_CHECKING:
    from himitsubako.backends.protocol import SecretBackend


def _resolve_backend() -> SecretBackend:
    """Resolve the BackendRouter from the nearest .himitsubako.yaml config.

    Returns a BackendRouter so all CLI commands transparently support
    per-credential routing. The router itself implements SecretBackend.
    """
    from pathlib import Path as _Path

    config_path = find_config(_Path.cwd())
    if config_path is None:
        raise click.ClickException("no .himitsubako.yaml found (run 'hmb init' first)")

    config = load_config(config_path)
    return BackendRouter(config, project_dir=config_path.parent)


def _stdout_is_tty() -> bool:
    """Indirection for testability — patched in tests to simulate TTY/pipe."""
    return sys.stdout.isatty()


@click.command("get")
@click.argument("key")
@click.option(
    "--reveal",
    "-r",
    is_flag=True,
    default=False,
    help="Print the secret to a terminal. Required when stdout is a TTY.",
)
def get_secret(key: str, reveal: bool) -> None:
    """Get a secret value by key."""
    try:
        backend = _resolve_backend()
        value = backend.get(key)
    except BackendError as exc:
        raise click.ClickException(str(exc)) from exc

    if value is None:
        click.echo(f"Secret '{key}' not found.", err=True)
        sys.exit(1)

    if _stdout_is_tty() and not reveal:
        click.echo(
            f"refusing to print secret '{key}' to a terminal without --reveal "
            f"(use 'hmb get {key} --reveal' or pipe to a consumer)",
            err=True,
        )
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
    except BackendError as exc:
        raise click.ClickException(str(exc)) from exc

    # Peek through the router to detect an unprefixed env default and warn.
    default = backend
    if isinstance(backend, BackendRouter):
        try:
            default = backend.resolve("__probe_for_default__")
        except BackendError:
            default = None
    if isinstance(default, EnvBackend) and not default.prefix:
        click.echo(
            "Warning: env backend has no prefix configured; "
            "listing all process environment variables. Set 'env.prefix' "
            "in .himitsubako.yaml to scope this to your application's keys.",
            err=True,
        )

    try:
        keys = backend.list_keys()
    except BackendError as exc:
        # Friendly handling for backends like keychain that cannot enumerate.
        click.echo(
            f"Backend '{exc.backend}' does not support listing: {exc.detail}",
            err=True,
        )
        click.echo(
            "See your project's secrets registry (.himitsubako.yaml) "
            "for the expected key names.",
            err=True,
        )
        return

    if not keys:
        click.echo("No secrets found.")
        return

    for key in sorted(keys):
        click.echo(key)
