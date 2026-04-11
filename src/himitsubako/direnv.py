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

from pathlib import Path  # noqa: TC003 — used at runtime in update_envrc

_START = "# --- himitsubako start ---"
_END = "# --- himitsubako end ---"
_HEADER_COMMENT = (
    "# himitsubako-managed — edits between markers will be overwritten by hmb"
)


def generate_envrc(secrets_file: str = ".secrets.enc.yaml") -> str:
    """Return the full content of a himitsubako-managed .envrc."""
    return (
        f"{_HEADER_COMMENT}\n"
        f"{_START}\n"
        f'eval "$(sops -d --output-type dotenv {secrets_file} 2>/dev/null | '
        "sed 's/^/export /')\" || true\n"
        f"{_END}\n"
    )


def _managed_block(secrets_file: str) -> str:
    """Return just the managed block (markers + body, no header comment)."""
    return (
        f"{_START}\n"
        f'eval "$(sops -d --output-type dotenv {secrets_file} 2>/dev/null | '
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
    if _START in existing and _END in existing:
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
