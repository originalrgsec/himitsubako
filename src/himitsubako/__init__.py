"""himitsubako — multi-backend credential abstraction for solo Python developers."""

from __future__ import annotations

from himitsubako.api import get, get_google_credentials, list_secrets, set_secret

__version__ = "0.9.0"

__all__ = [
    "__version__",
    "get",
    "get_google_credentials",
    "list_secrets",
    "set_secret",
]
