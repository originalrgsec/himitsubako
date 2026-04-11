"""hmb status — read-only config and backend diagnostic (HMB-S019).

Prints the active config path, default backend, SOPS binary and age
recipients, router table, and per-backend availability. Never calls
`get()` or `list_keys()` on any backend; availability is determined by
minimal ping-style checks (e.g. `sops --version`, `bw status`).
"""

from __future__ import annotations

import json as _json
import os
import subprocess
from pathlib import Path
from typing import Any

import click
import yaml

from himitsubako.config import find_config, load_config
from himitsubako.errors import BackendError, HimitsubakoError

_SOPS_BIN_ENV = "HIMITSUBAKO_SOPS_BIN"
_BW_BIN_ENV = "HIMITSUBAKO_BW_BIN"
_STATUS_SUBPROCESS_TIMEOUT = 5


def _resolve_sops_bin(config_bin: str | None) -> str:
    """Match HMB-S017 T-001 resolution order: env > config > PATH lookup."""
    env_val = os.environ.get(_SOPS_BIN_ENV, "").strip()
    if env_val:
        return env_val
    if config_bin:
        return config_bin
    return "sops"


def _read_sops_recipients(project_dir: Path) -> list[str]:
    """Parse age recipients from .sops.yaml. Returns [] on any problem."""
    sops_yaml = project_dir / ".sops.yaml"
    if not sops_yaml.exists():
        return []
    try:
        data = yaml.safe_load(sops_yaml.read_text())
    except (yaml.YAMLError, OSError):
        return []
    if not isinstance(data, dict):
        return []
    rules = data.get("creation_rules")
    if not isinstance(rules, list):
        return []
    recipients: list[str] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        age_val = rule.get("age")
        if not isinstance(age_val, str):
            continue
        for piece in age_val.split(","):
            piece = piece.strip()
            if piece:
                recipients.append(piece)
    return recipients


def _check_sops(bin_path: str) -> dict[str, str]:
    try:
        result = subprocess.run(
            [bin_path, "--version"],
            capture_output=True,
            text=True,
            timeout=_STATUS_SUBPROCESS_TIMEOUT,
            check=False,
        )
    except FileNotFoundError:
        return {"status": "unavailable", "detail": f"binary not found: {bin_path}"}
    except subprocess.TimeoutExpired:
        return {"status": "unavailable", "detail": "sops --version timed out"}
    except OSError as exc:
        return {"status": "unavailable", "detail": f"invoke failed: {exc}"}
    if result.returncode != 0:
        return {
            "status": "unavailable",
            "detail": f"sops --version exit {result.returncode}",
        }
    first_line = (result.stdout or "").strip().splitlines()
    version = first_line[0] if first_line else ""
    return {"status": "ok", "detail": version}


def _check_keychain(service: str) -> dict[str, str]:
    try:
        from himitsubako.backends.keychain import KeychainBackend

        KeychainBackend(service=service).check_availability()
    except BackendError as exc:
        return {"status": "unavailable", "detail": exc.detail}
    except Exception as exc:
        # Diagnostic tool: a broken keyring plugin must never crash status.
        return {"status": "unavailable", "detail": f"unexpected: {exc}"}
    return {"status": "ok", "detail": ""}


def _check_bitwarden(config_bin: str | None) -> dict[str, str]:
    bin_path = (
        os.environ.get(_BW_BIN_ENV, "").strip() or config_bin or "bw"
    )
    try:
        result = subprocess.run(
            [bin_path, "status"],
            capture_output=True,
            text=True,
            timeout=_STATUS_SUBPROCESS_TIMEOUT,
            check=False,
        )
    except FileNotFoundError:
        return {"status": "unavailable", "detail": f"binary not found: {bin_path}"}
    except subprocess.TimeoutExpired:
        return {"status": "unavailable", "detail": "bw status timed out"}
    except OSError as exc:
        return {"status": "unavailable", "detail": f"invoke failed: {exc}"}
    if result.returncode != 0:
        # Non-zero exit is authoritative: bw itself is signalling a problem.
        # Don't let parseable stdout override that into a false "ok".
        return {
            "status": "unavailable",
            "detail": f"bw status exit {result.returncode}",
        }
    lock_state = "unknown"
    try:
        parsed = _json.loads(result.stdout or "{}")
        if isinstance(parsed, dict):
            candidate = parsed.get("status")
            if isinstance(candidate, str):
                lock_state = candidate
    except ValueError:
        pass
    return {"status": "ok", "detail": f"vault {lock_state}"}


def _check_env() -> dict[str, str]:
    return {"status": "ok", "detail": ""}


def _collect_status() -> dict[str, Any]:
    config_path = find_config(Path.cwd())
    if config_path is None:
        return {
            "config_path": None,
            "default_backend": "env",
            "sops": None,
            "router": [],
            "backends": {"env": _check_env()},
        }

    config = load_config(config_path)
    project_dir = config_path.parent

    referenced: set[str] = {config.default_backend}
    for route in config.credentials.values():
        referenced.add(route.backend)

    sops_info: dict[str, Any] | None = None
    backends: dict[str, dict[str, str]] = {}

    if "sops" in referenced:
        bin_path = _resolve_sops_bin(config.sops.bin)
        sops_info = {
            "binary": bin_path,
            "recipients": _read_sops_recipients(project_dir),
        }
        backends["sops"] = _check_sops(bin_path)
    if "env" in referenced:
        backends["env"] = _check_env()
    if "keychain" in referenced:
        backends["keychain"] = _check_keychain(config.keychain.service)
    if "bitwarden-cli" in referenced:
        backends["bitwarden-cli"] = _check_bitwarden(config.bitwarden.bin)

    router = [
        {"pattern": pattern, "backend": route.backend}
        for pattern, route in config.credentials.items()
    ]

    return {
        "config_path": str(config_path),
        "default_backend": config.default_backend,
        "sops": sops_info,
        "router": router,
        "backends": backends,
    }


def _print_human(info: dict[str, Any]) -> None:
    if info["config_path"] is None:
        click.echo("Config: <not found>")
        click.echo("  searched: .himitsubako.yaml upward from cwd")
    else:
        click.echo(f"Config: {info['config_path']}")
    click.echo(f"Default backend: {info['default_backend']}")

    sops = info["sops"]
    if sops:
        click.echo("")
        click.echo("SOPS:")
        click.echo(f"  binary: {sops['binary']}")
        recipients = sops["recipients"]
        if recipients:
            click.echo(f"  recipients: {', '.join(recipients)}")
        else:
            click.echo("  recipients: <none — .sops.yaml missing or empty>")

    router = info["router"]
    if router:
        click.echo("")
        click.echo("Router:")
        for row in router:
            click.echo(f"  {row['pattern']} -> {row['backend']}")

    click.echo("")
    click.echo("Backends:")
    for name, result in info["backends"].items():
        line = f"  {name}: {result['status']}"
        if result["detail"]:
            line += f" ({result['detail']})"
        click.echo(line)


@click.command("status")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit the diagnostic as a single JSON object for scripting.",
)
def status(as_json: bool) -> None:
    """Print configuration and backend availability diagnostics.

    Read-only. Never calls get() or list_keys() on any backend; availability
    is determined by minimal ping-style checks. Exits 0 even if some backends
    are unavailable (unavailability is information, not an error). Exits 1
    only if the config file is malformed or cannot be parsed.
    """
    try:
        info = _collect_status()
    except HimitsubakoError as exc:
        raise click.ClickException(str(exc)) from exc

    if as_json:
        click.echo(_json.dumps(info, indent=2, sort_keys=True))
    else:
        _print_human(info)
