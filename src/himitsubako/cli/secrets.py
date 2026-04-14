"""hmb get, hmb set, hmb list — core secret management commands."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import click

from himitsubako.backends.env import EnvBackend
from himitsubako.config import find_config, load_config
from himitsubako.errors import BackendError, SecretNotFoundError
from himitsubako.router import BackendRouter

if TYPE_CHECKING:
    from himitsubako.backends.protocol import SecretBackend


from himitsubako.backends.google_oauth import REQUIRED_FIELDS as _GOOGLE_OAUTH_FIELDS


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
    """Set a secret value for a key.

    For google-oauth credentials, prompts separately for client_id,
    client_secret, and refresh_token (HMB-S030 AC-5). The `--value` flag
    is ignored in that case because a flat string cannot represent the
    three-field composite.
    """
    try:
        backend = _resolve_backend()
    except BackendError as exc:
        raise click.ClickException(str(exc)) from exc

    # Detect composite credentials (google-oauth) and fan out the prompts.
    resolved = backend
    if isinstance(backend, BackendRouter):
        try:
            resolved = backend.resolve(key)
        except BackendError as exc:
            raise click.ClickException(str(exc)) from exc

    if resolved.backend_name == "google-oauth":
        value = _prompt_google_oauth_value()
    elif value is None:
        value = click.prompt("Value", hide_input=True)

    try:
        resolved.set(key, value)
    except BackendError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Set '{key}'.")

    # Best-effort: ensure .envrc managed block exists when the resolved
    # default backend is sops. Failures here never break the set operation.
    _maybe_refresh_envrc()


def _prompt_google_oauth_value() -> str:
    """Prompt separately for the three google-oauth fields and return a JSON blob."""
    values: dict[str, str] = {}
    for field in _GOOGLE_OAUTH_FIELDS:
        values[field] = click.prompt(field, hide_input=True)
    return json.dumps(values)


def _maybe_refresh_envrc() -> None:
    """Update the project .envrc managed block if the default backend is sops."""
    from pathlib import Path as _Path

    from himitsubako.direnv import update_envrc

    try:
        config_path = find_config(_Path.cwd())
        if config_path is None:
            return
        config = load_config(config_path)
        if config.default_backend != "sops":
            return
        envrc_path = config_path.parent / ".envrc"
        update_envrc(envrc_path, secrets_file=config.sops.secrets_file)
    except (BackendError, OSError) as exc:
        click.echo(f"warning: could not refresh .envrc: {exc}", err=True)


@click.command("direnv-export")
def direnv_export() -> None:
    """Regenerate the himitsubako-managed block in .envrc."""
    from pathlib import Path as _Path

    from himitsubako.direnv import update_envrc

    config_path = find_config(_Path.cwd())
    if config_path is None:
        raise click.ClickException("no .himitsubako.yaml found (run 'hmb init' first)")

    config = load_config(config_path)
    envrc_path = config_path.parent / ".envrc"
    update_envrc(envrc_path, secrets_file=config.sops.secrets_file)
    click.echo(f"Updated {envrc_path}")


@click.command("delete")
@click.argument("key")
@click.option(
    "--force",
    "--yes",
    "force",
    is_flag=True,
    default=False,
    help="Skip the interactive confirmation prompt.",
)
@click.option(
    "--missing-ok",
    is_flag=True,
    default=False,
    help="Exit 0 silently if the key does not exist.",
)
def delete_secret(key: str, force: bool, missing_ok: bool) -> None:
    """Delete a secret by key.

    Exit codes:
        0  success (or confirmation declined, or --missing-ok hit)
        1  secret not found (unless --missing-ok)
        2  backend error (e.g. read-only backend, permission denied)
    """
    try:
        backend = _resolve_backend()
    except BackendError as exc:
        click.echo(f"Error: {exc.detail}", err=True)
        sys.exit(2)

    # Resolve once so the prompt names the target backend and the delete
    # dispatches directly to it (avoids a redundant router lookup between
    # prompt and dispatch).
    target = backend
    if isinstance(backend, BackendRouter):
        try:
            target = backend.resolve(key)
        except BackendError as exc:
            click.echo(f"Error: {exc.detail}", err=True)
            sys.exit(2)

    if not force:
        confirmed = click.confirm(
            f"Delete secret '{key}' from {target.backend_name}?",
            default=False,
        )
        if not confirmed:
            click.echo("Aborted.")
            return

    try:
        target.delete(key)
    except SecretNotFoundError:
        if missing_ok:
            return
        click.echo(f"Error: secret '{key}' not found", err=True)
        sys.exit(1)
    except BackendError as exc:
        click.echo(f"Error: {exc.detail}", err=True)
        sys.exit(2)

    click.echo(f"deleted {key}")


@click.command("list")
def list_secrets() -> None:
    """List all secret key names."""
    try:
        backend = _resolve_backend()
    except BackendError as exc:
        raise click.ClickException(str(exc)) from exc

    # Peek through the router to detect an unprefixed env default and warn.
    default: SecretBackend | None = backend
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
            "See your project's secrets registry (.himitsubako.yaml) for the expected key names.",
            err=True,
        )
        return

    if not keys:
        click.echo("No secrets found.")
        return

    for key in sorted(keys):
        click.echo(key)
