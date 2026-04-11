"""Shared fixtures for the HMB-S013 integration suite.

Every test module under `tests/integration/` is tagged with
`pytestmark = pytest.mark.integration` at the module level and is
excluded from the default `uv run pytest` invocation via the
`--ignore=tests/integration` addopts entry in `pyproject.toml`.

Run with: `uv run pytest tests/integration/`.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest
import yaml

if TYPE_CHECKING:
    from pathlib import Path

_REQUIRED_BINARIES = ("sops", "age", "age-keygen")


@pytest.fixture
def real_sops() -> None:
    """Skip the test if any required integration binary is missing."""
    missing = [b for b in _REQUIRED_BINARIES if shutil.which(b) is None]
    if missing:
        pytest.skip(
            f"integration test requires {', '.join(missing)} on PATH "
            "(install sops + age: https://github.com/getsops/sops, "
            "https://github.com/FiloSottile/age)"
        )


@pytest.fixture
def age_keypair(tmp_path: Path, real_sops: None) -> tuple[str, Path]:
    """Generate a throwaway age keypair and return (public_key, keys_file).

    The keys file is chmod'd to 0600. Callers typically export
    `SOPS_AGE_KEY_FILE=<keys_file>` so sops uses this key for decrypt.
    """
    keys_file = tmp_path / "age-key.txt"
    result = subprocess.run(
        ["age-keygen", "-o", str(keys_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"age-keygen failed: {result.stderr}")

    public_key = ""
    # age-keygen writes the pubkey comment to stderr on newer versions;
    # fall back to parsing the generated file for the comment line.
    for line in result.stderr.splitlines():
        if line.lower().startswith("public key:"):
            public_key = line.split(":", 1)[1].strip()
            break
    if not public_key:
        for line in keys_file.read_text().splitlines():
            if line.startswith("# public key:"):
                public_key = line.split(":", 1)[1].strip()
                break
    if not public_key:
        pytest.fail(
            "age-keygen did not surface a public key via stderr or "
            "the keys file comment"
        )

    keys_file.chmod(0o600)
    return public_key, keys_file


@pytest.fixture
def tmp_vault(
    tmp_path: Path,
    age_keypair: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Create a tmp project with real .himitsubako.yaml + .sops.yaml.

    - Writes `.sops.yaml` with the fixture age recipient.
    - Writes `.himitsubako.yaml` using the default SOPS backend.
    - Encrypts an empty `.secrets.enc.yaml` using real `sops`.
    - Exports `SOPS_AGE_KEY_FILE` for downstream decrypt calls.
    - `chdir`s into the vault so `find_config` and sops both resolve
      from there.

    Yields the vault directory path.
    """
    public_key, keys_file = age_keypair
    vault = tmp_path / "vault"
    vault.mkdir()

    (vault / ".sops.yaml").write_text(
        yaml.safe_dump(
            {
                "creation_rules": [
                    {
                        "path_regex": r"\.secrets\.enc\.yaml$",
                        "age": public_key,
                    }
                ]
            }
        )
    )
    (vault / ".himitsubako.yaml").write_text(
        yaml.safe_dump(
            {
                "default_backend": "sops",
                "sops": {"secrets_file": ".secrets.enc.yaml"},
            }
        )
    )

    secrets_file = vault / ".secrets.enc.yaml"
    secrets_file.write_text(yaml.safe_dump({}))

    monkeypatch.setenv("SOPS_AGE_KEY_FILE", str(keys_file))
    # Remove any PROJECT-scoped SOPS_AGE_RECIPIENTS that a developer may
    # have exported in their shell — we only want this fixture's recipient.
    monkeypatch.delenv("SOPS_AGE_RECIPIENTS", raising=False)
    monkeypatch.chdir(vault)

    # Always pass --filename-override, mirroring production code in
    # SopsBackend._encrypt. Even though the path regex matches the real
    # filename here (because we're operating on the file directly, not a
    # mkstemp tempfile), the fixture should not accidentally sidestep
    # the original HMB-S013 bug — pairing it with production reduces
    # the chance of a future refactor silently regressing.
    encrypt = subprocess.run(
        [
            "sops",
            "--encrypt",
            "--filename-override",
            str(secrets_file),
            "--in-place",
            str(secrets_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if encrypt.returncode != 0:
        pytest.fail(
            f"sops --encrypt bootstrap failed: {encrypt.stderr or encrypt.stdout}"
        )

    return vault


@pytest.fixture
def second_age_keypair(tmp_path: Path, real_sops: None) -> tuple[str, Path]:
    """A second throwaway keypair for rotate-key tests.

    Distinct from `age_keypair` because rotate needs old + new keys to
    coexist during the swap.
    """
    keys_file = tmp_path / "age-key-new.txt"
    result = subprocess.run(
        ["age-keygen", "-o", str(keys_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"age-keygen (second) failed: {result.stderr}")

    public_key = ""
    for line in result.stderr.splitlines():
        if line.lower().startswith("public key:"):
            public_key = line.split(":", 1)[1].strip()
            break
    if not public_key:
        for line in keys_file.read_text().splitlines():
            if line.startswith("# public key:"):
                public_key = line.split(":", 1)[1].strip()
                break
    if not public_key:
        pytest.fail(
            "second age-keygen did not surface a public key via stderr or "
            "the keys file comment"
        )
    keys_file.chmod(0o600)
    return public_key, keys_file
