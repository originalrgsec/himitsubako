"""Tests for the SecretBackend protocol."""

from __future__ import annotations


class TestSecretBackendProtocol:
    """Verify the protocol is importable and structurally checkable."""

    def test_protocol_is_importable(self):
        from himitsubako.backends.protocol import SecretBackend

        assert SecretBackend is not None

    def test_protocol_is_runtime_checkable(self):
        from himitsubako.backends.protocol import SecretBackend

        # Protocol decorated with @runtime_checkable should support isinstance checks
        assert hasattr(SecretBackend, "__protocol_attrs__") or callable(
            getattr(SecretBackend, "__instancecheck__", None)
        )

    def test_conforming_class_is_recognized(self):
        from himitsubako.backends.protocol import SecretBackend

        class FakeBackend:
            def get(self, key: str) -> str | None:
                return None

            def set(self, key: str, value: str) -> None:
                pass

            def delete(self, key: str) -> None:
                pass

            def list_keys(self) -> list[str]:
                return []

            @property
            def backend_name(self) -> str:
                return "fake"

        assert isinstance(FakeBackend(), SecretBackend)

    def test_non_conforming_class_is_rejected(self):
        from himitsubako.backends.protocol import SecretBackend

        class Incomplete:
            def get(self, key: str) -> str | None:
                return None

        assert not isinstance(Incomplete(), SecretBackend)
