"""hmb rotate (credential value) and hmb rotate-key (age master key).

Three distinct commands/modes, deliberately kept in the same module so
the distinction is visible at a glance:

- `hmb rotate <credential>` (HMB-S021) rotates the VALUE of a single
  credential by routing through BackendRouter, then writes one JSON
  Lines entry to `~/.himitsubako/audit.log`.
- `hmb rotate <google-oauth-credential>` (HMB-S032) runs an OAuth
  device flow (default) or InstalledAppFlow (`--browser`), writes the
  new refresh token back to the storage backend, and audits the method.
- `hmb rotate-key` (HMB-S005) re-encrypts the secrets file under a new
  age master key using `sops updatekeys`.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import click
import yaml

from himitsubako._redaction import redact_tokens
from himitsubako.audit import write_audit_entry
from himitsubako.backends.google_oauth import GoogleOAuthBackend
from himitsubako.config import find_config, load_config
from himitsubako.errors import BackendError
from himitsubako.google_oauth_rotate import run_device_flow, run_installed_app_flow
from himitsubako.router import BackendRouter

_SOPS_SUBPROCESS_TIMEOUT = 30
_ENV_SOPS_BIN = "HIMITSUBAKO_SOPS_BIN"


def _resolve_sops_bin() -> str:
    """Match HMB-S017 T-001 resolution order: env var > 'sops' on PATH.

    Used by `hmb rotate-key` and `hmb init`, which do not have a loaded
    HimitsubakoConfig in scope (rotate-key reads .sops.yaml directly;
    init creates the config). For backend operations through
    SopsBackend, the backend's own _resolve_sops_bin handles the
    additional config-arg layer.
    """
    return os.environ.get(_ENV_SOPS_BIN, "").strip() or "sops"


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


def _rules_with_age(sops_config_data: object) -> list[dict]:
    """Return the list of creation_rules dicts that contain an `age` field.

    HMB-S040: multi-rule safety requires counting how many rules have an
    `age` recipient so we can distinguish the single-rule (safe) case
    from the multi-rule (requires --rule) case.
    """
    if not isinstance(sops_config_data, dict):
        return []
    rules = sops_config_data.get("creation_rules")
    if not isinstance(rules, list):
        return []
    return [r for r in rules if isinstance(r, dict) and "age" in r]


def _format_rule_list(rules: list[dict]) -> str:
    """Human-readable bullet list of rule path_regex + current age recipient.

    Used in error messages when rotate-key refuses to act on a multi-rule
    .sops.yaml or when --rule fails to match.
    """
    lines = []
    for rule in rules:
        regex = rule.get("path_regex", "<no path_regex>")
        age = rule.get("age", "<no age>")
        lines.append(f"    - path_regex: {regex}\n      age: {age}")
    return "\n".join(lines)


@click.command("rotate-key")
@click.option(
    "--new-key",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the new age keys file.",
)
@click.option("--dry-run", is_flag=True, help="Show what would change without modifying files.")
@click.option(
    "--rule",
    "rule_pattern",
    default=None,
    help=(
        "When .sops.yaml has multiple creation_rules, select which rule's "
        "age recipient to rotate. The value is a regular expression matched "
        "against each rule's path_regex; the match must resolve to exactly "
        "one rule. Required if .sops.yaml has more than one rule with an "
        "age field."
    ),
)
def rotate_key(new_key: Path, dry_run: bool, rule_pattern: str | None) -> None:
    """Re-encrypt secrets with a new age key."""
    new_public_key = _read_public_key(new_key)

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

    # HMB-S040 multi-rule safety: decide which rule(s) to update. The
    # previous implementation blindly overwrote every rule's `age`
    # field, silently collapsing multi-key configurations to one key.
    sops_config_data = yaml.safe_load(sops_yaml.read_text())
    age_rules = _rules_with_age(sops_config_data)

    if not age_rules:
        # Nothing with an age recipient — write the file unchanged (other
        # keys like pgp may still be present and are left alone).
        rules_to_update: list[dict] = []
    elif len(age_rules) == 1 and rule_pattern is None:
        # Single-rule case: behaviour unchanged (AC-1).
        rules_to_update = age_rules
    elif rule_pattern is None:
        # Multi-rule without --rule: refuse to act. Silent overwrite is
        # the bug we are fixing.
        raise click.ClickException(
            ".sops.yaml has multiple creation_rules with an age recipient. "
            "Use --rule <path_regex> to select which rule to rotate.\n"
            "Rules found:\n" + _format_rule_list(age_rules)
        )
    else:
        # --rule supplied: match against each rule's path_regex. Require
        # exactly one match; zero or many both indicate operator error.
        try:
            compiled = re.compile(rule_pattern)
        except re.error as exc:
            raise click.ClickException(
                f"invalid --rule regular expression {rule_pattern!r}: {exc}"
            ) from exc

        matched = [r for r in age_rules if compiled.search(str(r.get("path_regex", "")))]
        if not matched:
            raise click.ClickException(
                f"--rule {rule_pattern!r} matched no creation_rule path_regex.\n"
                "Available rules:\n" + _format_rule_list(age_rules)
            )
        if len(matched) > 1:
            raise click.ClickException(
                f"--rule {rule_pattern!r} matched {len(matched)} rules; "
                "must match exactly one.\nMatched rules:\n" + _format_rule_list(matched)
            )
        rules_to_update = matched

    for rule in rules_to_update:
        rule["age"] = new_public_key
    _atomic_write_yaml(sops_yaml, sops_config_data)
    if len(rules_to_update) == 1:
        click.echo(
            f"  Updated .sops.yaml rule {rules_to_update[0].get('path_regex')!r} "
            f"with new key: {new_public_key}"
        )
    else:
        click.echo(f"  Updated .sops.yaml with new key: {new_public_key}")

    # Re-encrypt secrets file with sops
    if secrets_path.exists():
        sops_bin = _resolve_sops_bin()
        try:
            result = subprocess.run(
                [
                    sops_bin,
                    "updatekeys",
                    "--yes",
                    str(secrets_path),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=_SOPS_SUBPROCESS_TIMEOUT,
            )
        except FileNotFoundError as exc:
            raise click.ClickException(
                f"sops binary not found at '{sops_bin}'. Install: https://github.com/getsops/sops"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise click.ClickException(
                f"sops updatekeys timed out after {_SOPS_SUBPROCESS_TIMEOUT}s"
            ) from exc

        if result.returncode != 0:
            raise click.ClickException(f"sops updatekeys failed: {redact_tokens(result.stderr)}")

        click.echo(f"  Re-encrypted {secrets_file}")
    else:
        click.echo(f"  Skip {secrets_file} (file does not exist)")

    click.echo("Key rotation complete.")


def _atomic_write_yaml(path: Path, data: dict) -> None:
    """Write a YAML document atomically via tempfile + os.replace.

    Protects against truncation on SIGKILL or disk-full mid-write. The
    tempfile is created in the same directory so os.replace() is atomic
    under POSIX (rename within a single filesystem). On exception the
    tempfile is unlinked.
    """
    fd, tmp_name = tempfile.mkstemp(suffix=".yaml", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        try:
            tmp_file = os.fdopen(fd, "w")
        except Exception:
            os.close(fd)
            raise
        with tmp_file:
            yaml.dump(data, tmp_file, default_flow_style=False)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    tmp_path.replace(path)


@click.command("rotate")
@click.argument("credential")
@click.option(
    "--value-from-file",
    default=None,
    type=click.Path(),
    help="Read the new value from a file instead of stdin.",
)
@click.option(
    "--browser",
    is_flag=True,
    default=False,
    help="(google-oauth only) Use InstalledAppFlow with a local browser instead of device flow.",
)
def rotate_credential(credential: str, value_from_file: str | None, browser: bool) -> None:
    """Rotate a credential's VALUE and append an audit log entry.

    Different from `hmb rotate-key`: this rotates one credential's value,
    while `hmb rotate-key` re-encrypts the secrets file under a new age
    master key.

    For regular credentials, reads the new value from stdin (or
    --value-from-file) and writes it through the resolved backend.

    For google-oauth credentials (HMB-S030), runs an OAuth authorization
    flow to obtain a fresh refresh token and writes it back to the
    configured storage backend. Defaults to device flow (works over
    SSH); use --browser for InstalledAppFlow on a desktop.
    """
    # 1. Resolve the vault config and the target backend up front.
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

    # 2. Branch on credential type. google-oauth gets the OAuth flow;
    #    everything else reads the new value from stdin/file.
    if isinstance(target, GoogleOAuthBackend):
        _rotate_google_oauth(
            credential=credential,
            target=target,
            use_browser=browser,
            config_path=config_path,
        )
        return

    if browser:
        click.echo(
            "Error: --browser is only valid for google-oauth credentials.",
            err=True,
        )
        sys.exit(2)

    new_value = _read_rotation_value(value_from_file)

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


def _read_rotation_value(value_from_file: str | None) -> str:
    """Read the new rotation value from file or stdin. TTY stdin is refused."""
    if value_from_file is not None:
        file_path = Path(value_from_file)
        if not file_path.exists():
            click.echo(f"Error: file not found: {value_from_file}", err=True)
            sys.exit(2)
        try:
            return file_path.read_text().rstrip("\r\n")
        except OSError as exc:
            click.echo(f"Error: cannot read {value_from_file}: {exc}", err=True)
            sys.exit(2)

    if _stdin_is_tty():
        click.echo(
            "refusing to read a secret from a TTY. "
            "Pipe the new value on stdin, or use --value-from-file <path>.",
            err=True,
        )
        sys.exit(2)
    return sys.stdin.read().rstrip("\r\n")


def _rotate_google_oauth(
    credential: str,
    target: GoogleOAuthBackend,
    use_browser: bool,
    config_path: Path,
) -> None:
    """Run OAuth rotation for a google-oauth credential."""
    method = "browser" if use_browser else "device"
    backend_name = target.backend_name

    # Read current client_id and client_secret. A partial credential (missing
    # or corrupt refresh_token) is a valid starting point for rotation as long
    # as the client credentials are present, so fall back to reading each
    # field individually if the composite get() raises.
    client_id, client_secret = _read_google_client_credentials(target, credential)

    if not client_id or not client_secret:
        click.echo(
            "Error: rotation requires existing client_id and client_secret. "
            f"Run `hmb set {credential}` to populate them first.",
            err=True,
        )
        sys.exit(1)

    # Run the OAuth flow.
    try:
        if use_browser:
            result = run_installed_app_flow(
                client_id=client_id,
                client_secret=client_secret,
                scopes=target.scopes,
            )
        else:
            result = run_device_flow(
                client_id=client_id,
                client_secret=client_secret,
                scopes=target.scopes,
            )
    except BackendError as exc:
        with contextlib.suppress(OSError):
            write_audit_entry(
                command="rotate",
                credential=credential,
                backend=backend_name,
                outcome="failure",
                vault_path=config_path,
                error=redact_tokens(f"{method}:{exc.detail}"),
            )
        click.echo(f"Error: {exc.detail}", err=True)
        sys.exit(1)

    # Build the new JSON blob: unchanged client_id/client_secret + new refresh_token.
    new_blob = json.dumps(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": result.refresh_token,
        }
    )

    try:
        target.set(credential, new_blob)
    except BackendError as exc:
        # Write failure happens AFTER we have a new refresh token from Google
        # but could not store it. Tell the user to retry; Google has not
        # revoked the old token on their side.
        with contextlib.suppress(OSError):
            write_audit_entry(
                command="rotate",
                credential=credential,
                backend=backend_name,
                outcome="failure",
                vault_path=config_path,
                error=redact_tokens(f"{method}:storage_write_failed:{exc.detail}"),
            )
        click.echo(
            f"Error: OAuth succeeded but storage write failed: {exc.detail}. "
            "The old refresh token is still valid; re-run `hmb rotate` to retry.",
            err=True,
        )
        sys.exit(1)

    try:
        write_audit_entry(
            command="rotate",
            credential=credential,
            backend=backend_name,
            outcome="success",
            vault_path=config_path,
            method=method,
        )
    except OSError as exc:
        click.echo(
            f"WARN: rotation succeeded but audit log write failed: {exc}",
            err=True,
        )

    click.echo(f"rotated {credential} ({method} flow)")


def _read_google_client_credentials(
    target: GoogleOAuthBackend, credential: str
) -> tuple[str | None, str | None]:
    """Return (client_id, client_secret) for a google-oauth credential.

    Prefers the composite get() path, which raises if any field is missing.
    Falls back to per-field reads so rotation works even when the stored
    refresh_token is missing or corrupt — the common case for rotation.
    Returns (None, None) for any field that cannot be read.
    """
    try:
        current = target.get(credential)
    except BackendError:
        current = None

    if current is not None:
        parsed = json.loads(current)
        client_id = parsed.get("client_id")
        client_secret = parsed.get("client_secret")
        return (
            client_id if isinstance(client_id, str) else None,
            client_secret if isinstance(client_secret, str) else None,
        )

    # Composite read failed (likely because refresh_token is absent). Read
    # each required field individually so rotation can still recover.
    try:
        client_id = target.get_field("client_id")
    except BackendError:
        client_id = None
    try:
        client_secret = target.get_field("client_secret")
    except BackendError:
        client_secret = None
    return client_id, client_secret
