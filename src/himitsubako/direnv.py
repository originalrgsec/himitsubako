"""direnv integration helper (HMB-S010).

Generates and updates `.envrc` files so SOPS-decrypted secrets are
auto-exported into the shell when entering a project directory.

The managed block is delimited by `# --- himitsubako start ---` and
`# --- himitsubako end ---` markers. `update_envrc` preserves any user
lines outside the markers and replaces (or inserts) the managed block.

The block uses `sops -d --output-type dotenv` so we do not need `yq` or
any other parser. The decryption happens at shell-load time, so the
.envrc never contains plaintext credentials and never needs to be
regenerated when individual secrets change.
"""

from __future__ import annotations

import shlex
from pathlib import Path  # noqa: TC003 — used at runtime in update_envrc

from himitsubako.errors import BackendError

_START = "# --- himitsubako start ---"
_END = "# --- himitsubako end ---"
_HEADER_COMMENT = "# himitsubako-managed — edits between markers will be overwritten by hmb"


def generate_envrc(secrets_file: str = ".secrets.enc.yaml") -> str:
    """Return the full content of a himitsubako-managed .envrc."""
    quoted = shlex.quote(secrets_file)
    return (
        f"{_HEADER_COMMENT}\n"
        f"{_START}\n"
        f'eval "$(sops -d --output-type dotenv {quoted} 2>/dev/null | '
        "sed 's/^/export /')\" || true\n"
        f"{_END}\n"
    )


def _managed_block(secrets_file: str) -> str:
    """Return just the managed block (markers + body, no header comment).

    The secrets_file path is shell-quoted with shlex.quote so a path
    containing spaces, dollar signs, backticks, or other shell
    metacharacters cannot break out of the eval line. This is defense
    in depth — operators control this value via .himitsubako.yaml — but
    it eliminates an entire class of injection risk.
    """
    quoted = shlex.quote(secrets_file)
    return (
        f"{_START}\n"
        f'eval "$(sops -d --output-type dotenv {quoted} 2>/dev/null | '
        "sed 's/^/export /')\" || true\n"
        f"{_END}\n"
    )


def update_envrc(envrc_path: Path, secrets_file: str = ".secrets.enc.yaml") -> None:
    """Insert or replace the himitsubako-managed block in .envrc.

    User-added lines outside the managed markers are preserved verbatim.
    If the file does not exist, it is created with just the managed block.
    Idempotent: calling repeatedly with the same arguments produces the
    same file content.
    """
    new_block = _managed_block(secrets_file)

    if not envrc_path.exists():
        envrc_path.write_text(generate_envrc(secrets_file))
        return

    existing = envrc_path.read_text()

    start_count = existing.count(_START)
    end_count = existing.count(_END)
    if start_count > 1 or end_count > 1:
        raise BackendError(
            "direnv",
            f".envrc contains {start_count} start markers and {end_count} "
            "end markers; resolve duplicates manually before running this command",
        )

    if start_count == 1 and end_count == 1:
        # Replace the existing managed block in place. Try the trailing-\n
        # variant first; only fall back to bare _END if the file's last
        # marker really has no newline after it.
        before, _, rest = existing.partition(_START)
        _body, sep, after = rest.partition(_END + "\n")
        if not sep:
            _body, sep, after = rest.partition(_END)
        new_content = before + new_block + after
    else:
        # No markers yet — append the managed block at the end
        sep_nl = "" if existing.endswith("\n") else "\n"
        new_content = existing + sep_nl + new_block

    envrc_path.write_text(new_content)
