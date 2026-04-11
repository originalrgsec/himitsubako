"""HMB-S013: BackendRouter against real SOPS + env backends.

Default backend is SOPS; `CI_*` keys route to the env backend. Verifies
the router dispatches to each concrete backend correctly when both are
real (no mocks).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

if TYPE_CHECKING:
    from pathlib import Path

from himitsubako.backends.sops import SopsBackend
from himitsubako.config import find_config, load_config
from himitsubako.router import BackendRouter

pytestmark = pytest.mark.integration


@pytest.fixture
def routed_vault(
    tmp_vault: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Override `.himitsubako.yaml` to declare a `CI_*` env route alongside
    the SOPS default. `tmp_vault` already supplies a working .sops.yaml and
    encrypted secrets file."""
    # Note: no env.prefix here. If the router sends key `CI_TOKEN` to
    # an env backend configured with `prefix: CI_`, the env backend
    # would strip the prefix and look up `TOKEN` — the opposite of what
    # we want. Route on the raw name, no stripping.
    config = {
        "default_backend": "sops",
        "sops": {"secrets_file": ".secrets.enc.yaml"},
        "credentials": {
            "CI_*": {"backend": "env"},
        },
    }
    (tmp_vault / ".himitsubako.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False)
    )
    # Seed a real env var the router should pick up for CI_ keys.
    monkeypatch.setenv("CI_TOKEN", "from-env-routed")
    return tmp_vault


class TestRouterRealDispatch:
    def test_sops_default_and_ci_env_route(
        self, routed_vault: Path
    ) -> None:
        # Seed a SOPS-backed secret first so we can verify it hits SOPS.
        sops_backend = SopsBackend(secrets_file=".secrets.enc.yaml")
        sops_backend.set("APP_SECRET", "sops-value")

        config_path = find_config(routed_vault)
        assert config_path is not None
        config = load_config(config_path)
        router = BackendRouter(config, project_dir=routed_vault)

        assert router.get("APP_SECRET") == "sops-value"
        assert router.get("CI_TOKEN") == "from-env-routed"

        # Resolved backend for each key is the correct concrete class.
        resolved_app = router.resolve("APP_SECRET")
        resolved_ci = router.resolve("CI_TOKEN")
        assert resolved_app.backend_name == "sops"
        assert resolved_ci.backend_name == "env"

    def test_router_list_aggregates_both_backends(
        self,
        routed_vault: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sops_backend = SopsBackend(secrets_file=".secrets.enc.yaml")
        sops_backend.set("SOPS_ONLY", "x")

        # Clear *every* CI_* var from the parent env so the list
        # assertion below is closed over the fixture's two vars only.
        # Developer / CI shells commonly export CI_COMMIT_REF,
        # CI_PIPELINE_ID, CI_JOB_*, etc., and the env backend (no prefix
        # here) returns them all.
        import os as _os

        for k in [k for k in list(_os.environ) if k.startswith("CI_")]:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("CI_TOKEN", "from-env-routed")
        monkeypatch.setenv("CI_RUN_ID", "run-42")

        config_path = find_config(routed_vault)
        assert config_path is not None
        config = load_config(config_path)
        router = BackendRouter(config, project_dir=routed_vault)

        keys = set(router.list_keys())
        assert "SOPS_ONLY" in keys
        # env backend has no prefix configured in this fixture, so it
        # returns the raw env-var names (including ones from the real
        # parent process environment).
        assert "CI_TOKEN" in keys
        assert "CI_RUN_ID" in keys

    def test_routed_delete_against_read_only_env_raises(
        self, routed_vault: Path
    ) -> None:
        from himitsubako.errors import BackendError

        config_path = find_config(routed_vault)
        assert config_path is not None
        config = load_config(config_path)
        router = BackendRouter(config, project_dir=routed_vault)

        with pytest.raises(BackendError, match="read-only"):
            router.delete("CI_TOKEN")
