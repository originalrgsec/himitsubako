"""Tests for the top-level package."""

from __future__ import annotations


class TestPackageInit:
    """Verify the package is importable and exposes expected attributes."""

    def test_package_is_importable(self):
        import himitsubako

        assert himitsubako is not None

    def test_version_is_string(self):
        from himitsubako import __version__

        assert isinstance(__version__, str)
        assert len(__version__) > 0

    def test_backends_package_is_importable(self):
        import himitsubako.backends

        assert himitsubako.backends is not None
