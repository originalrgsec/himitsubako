"""himitsubako — multi-backend credential abstraction for solo Python developers."""

from __future__ import annotations

from himitsubako.api import get, list_secrets, set_secret

__version__ = "0.4.0"

__all__ = ["__version__", "get", "list_secrets", "set_secret"]
