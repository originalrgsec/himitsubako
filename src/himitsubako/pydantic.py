"""pydantic-settings source for himitsubako (HMB-S011).

`HimitsubakoSettingsSource` is a custom `PydanticBaseSettingsSource`
that pulls each field's value from a himitsubako backend (or
BackendRouter, transparently). It is meant to be slotted into a
`settings_customise_sources` chain so a single settings model can mix
backends — `db_password` from SOPS, `oauth_client_secret` from
Keychain, etc., all routed by the project's `.himitsubako.yaml`.

Recommended source order (decision 6, 2026-04-11):

    init kwargs > explicit env vars > HimitsubakoSettingsSource >
    dotenv files > file_secret > defaults

Rationale: env vars still win for one-off operator overrides, but
himitsubako is the canonical source rather than a fallback. Override
this in your application's `settings_customise_sources` if you have
different needs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from himitsubako.errors import BackendError

if TYPE_CHECKING:
    from himitsubako.backends.protocol import SecretBackend

# pydantic-settings is an optional dependency under the [pydantic-settings] extra.
try:
    from pydantic_settings import PydanticBaseSettingsSource

    _PYDANTIC_SETTINGS_AVAILABLE = True
    _PYDANTIC_SETTINGS_IMPORT_ERROR: Exception | None = None
except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
    PydanticBaseSettingsSource = object  # type: ignore[assignment,misc]
    _PYDANTIC_SETTINGS_AVAILABLE = False
    _PYDANTIC_SETTINGS_IMPORT_ERROR = exc


def _require_pydantic_settings() -> None:
    if not _PYDANTIC_SETTINGS_AVAILABLE:
        raise BackendError(
            "pydantic-settings",
            "the pydantic-settings integration requires the "
            "[pydantic-settings] extra; install with "
            "'pip install himitsubako[pydantic-settings]'",
        ) from _PYDANTIC_SETTINGS_IMPORT_ERROR


class HimitsubakoSettingsSource(PydanticBaseSettingsSource):
    """Pull settings field values from himitsubako backends.

    Construct one of these inside your settings model's
    `settings_customise_sources` classmethod and slot it into the chain
    where it makes sense for your override semantics. The recommended
    position is after `env_settings` and before `dotenv_settings`.
    """

    def __init__(
        self,
        settings_cls: Any,
        backend: SecretBackend | None = None,
        prefix: str = "",
    ) -> None:
        _require_pydantic_settings()
        super().__init__(settings_cls)
        self._backend = backend
        self._prefix = prefix

    def _resolve_backend(self) -> SecretBackend:
        if self._backend is not None:
            return self._backend
        # Lazy import to avoid pulling in the api module at class-definition time.
        from himitsubako.api import _resolve_backend

        self._backend = _resolve_backend()
        return self._backend

    def get_field_value(
        self, field: Any, field_name: str
    ) -> tuple[Any, str, bool]:
        """Look up a single field value. Required by PydanticBaseSettingsSource."""
        backend = self._resolve_backend()
        lookup_key = f"{self._prefix}{field_name}"
        value = backend.get(lookup_key)
        return value, field_name, False

    def prepare_field_value(
        self,
        field_name: str,
        field: Any,
        value: Any,
        value_is_complex: bool,
    ) -> Any:
        return value

    def __call__(self) -> dict[str, Any]:
        """Return a dict of field names to resolved values.

        Fields where himitsubako has no value are omitted from the dict
        so other sources in the chain can provide them.
        """
        result: dict[str, Any] = {}
        for field_name, field in self.settings_cls.model_fields.items():
            value, _, _ = self.get_field_value(field, field_name)
            if value is not None:
                result[field_name] = value
        return result
