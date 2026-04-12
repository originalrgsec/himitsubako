"""Append-only audit log for credential rotation events (HMB-S021).

Writes one JSON Lines entry per event to `~/.himitsubako/audit.log` by
default. The caller chooses the location via the `log_path` kwarg; the
default is exposed as `AUDIT_LOG` so it can be monkeypatched in tests
and overridden via config in future stories.

Design decisions (see stories/HMB-S021-rotate-audit-log.md for the full
rationale):

1. **User-level, not vault-scoped.** A developer with multiple vaults
   benefits from a single rotation history spanning all of them.
2. **JSON Lines, not TSV or plaintext.** Structured fields survive
   schema evolution without breaking downstream parsers.
3. **Atomic append via `O_APPEND` + single `write()`.** POSIX guarantees
   atomic append for writes under `PIPE_BUF` (4 KiB); a JSON line plus
   newline is well under that limit. Concurrent writers from separate
   processes interleave cleanly, one full line at a time.
4. **Mode 0700 on the directory, 0600 on the log file when created.**
   Existing modes are preserved — the module does not chmod down on
   every write.
5. **No rotation, retention, or truncation in v0.4.0.** The log grows
   unbounded. Users manage it with `logrotate` or manual truncation.
6. **Error strings are redacted** (40+-char base64-alphabet substrings
   replaced with `[REDACTED]`) before being written, via the shared
   `_redaction.redact_tokens` helper from HMB-S009.

Callers are responsible for deciding whether an `OSError` from
`write_audit_entry` should surface to the user or be swallowed: the CLI
command `hmb rotate` swallows it (with a stderr warning) because losing
an audit line is less bad than rolling back a successful rotation.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from himitsubako._redaction import redact_tokens

AUDIT_DIR: Path = Path.home() / ".himitsubako"
AUDIT_LOG: Path = AUDIT_DIR / "audit.log"

Outcome = Literal["success", "failure"]

_DIR_MODE = 0o700
_FILE_MODE = 0o600


def _ensure_audit_dir(directory: Path) -> None:
    """Create the audit directory with mode 0700 if it does not exist.

    Uses ``exist_ok=True`` so a concurrent writer that creates the
    directory between our check and our ``mkdir`` does not race us into
    a ``FileExistsError``. ``exist_ok`` does not alter the mode of an
    already-present directory, so the "do not chmod down on every write"
    invariant is preserved.
    """
    directory.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)


def write_audit_entry(
    *,
    command: str,
    credential: str,
    backend: str,
    outcome: Outcome,
    vault_path: Path,
    error: str | None = None,
    log_path: Path | None = None,
) -> None:
    """Append a single JSONL audit entry to the audit log.

    Arguments are keyword-only to prevent positional misordering that
    could put a credential name in the value slot or vice versa.

    Raises:
        OSError: If the directory or file cannot be created, or if the
            atomic append fails. The caller decides whether to surface
            this to the user or degrade gracefully.
    """
    target = log_path if log_path is not None else AUDIT_LOG

    entry: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "command": command,
        "credential": credential,
        "backend": backend,
        "outcome": outcome,
        "vault_path": str(vault_path),
        "pid": os.getpid(),
    }
    if error is not None:
        entry["error"] = redact_tokens(error)

    # One JSON object per line. Sort keys for deterministic output —
    # makes diff-based testing and grep-based analysis saner.
    line = json.dumps(entry, sort_keys=True) + "\n"
    encoded = line.encode("utf-8")

    _ensure_audit_dir(target.parent)

    # O_APPEND on a local POSIX filesystem makes the seek-to-end and
    # write atomic with respect to other O_APPEND writers on the same
    # file. The invariant is that a single write() syscall holds the
    # append lock — splitting the write across two calls would break
    # atomicity even with O_APPEND. JSON Lines entries here are well
    # under 1 KiB in practice.
    #
    # O_CREAT with mode 0600 applies the mode only when the file does
    # not already exist; existing permissions are preserved.
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    fd = os.open(target, flags, _FILE_MODE)
    try:
        os.write(fd, encoded)
    finally:
        os.close(fd)
