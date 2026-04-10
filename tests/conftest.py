"""Shared test fixtures for himitsubako."""

from __future__ import annotations

import pytest
import yaml

SOPS_CONFIG = {
    "default_backend": "sops",
    "sops": {"secrets_file": ".secrets.enc.yaml"},
}

SOPS_CREATION_RULES = {
    "creation_rules": [
        {"path_regex": r"\.secrets\.enc\.yaml$", "age": "age1oldkey123"},
    ],
}


def write_sops_config(path):
    """Write a standard .himitsubako.yaml to the given directory."""
    (path / ".himitsubako.yaml").write_text(yaml.dump(SOPS_CONFIG))


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with a .himitsubako.yaml config."""
    write_sops_config(tmp_path)
    return tmp_path
