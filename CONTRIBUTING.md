# Contributing to himitsubako

## Development setup

himitsubako uses [uv](https://github.com/astral-sh/uv) for dependency management. The venv lives at `.venv/` in the project root.

```sh
git clone https://github.com/originalrgsec/himitsubako.git
cd himitsubako
uv sync --all-extras --dev
```

`--all-extras` pulls in the `keychain`, `pydantic-settings`, `docs`, and `publish` extras alongside `dev` so every code path is importable in local testing.

## Running tests

The test suite is split into a fast unit layer and an opt-in integration layer. Both run against the shipped source.

### Unit tests (default)

```sh
uv run pytest
```

190+ tests, runs in under a second. This is what the default `pytest` invocation does because `pyproject.toml` sets `addopts = "... --ignore=tests/integration"`. Every unit test mocks out `subprocess.run` and never touches real binaries, files outside `tmp_path`, or network.

### Coverage

```sh
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80
```

The 80% gate is enforced on the unit suite only. The integration suite contributes its own coverage but does not gate the unit run.

### Integration tests (opt-in)

The integration suite exercises real binaries and real filesystem state. It is excluded from the default run but runs cleanly when you ask for it.

```sh
# Everything runnable on this machine:
uv run pytest tests/integration/

# The CI-runnable subset (S013 — sops + env only, no OS-specific binaries):
uv run pytest tests/integration/ -m "integration and not macos and not bitwarden and not direnv"

# Per-backend local-only subsets (S020):
uv run pytest tests/integration/ -m "integration and macos"     # macOS Keychain
uv run pytest tests/integration/ -m "integration and direnv"    # direnv binary
uv run pytest tests/integration/ -m "integration and bitwarden" # bw CLI, see below
```

#### Bitwarden CLI tests

The `bitwarden` marker requires deliberate opt-in via the `HMB_TEST_BW_SESSION` environment variable (separate from the real `BW_SESSION` so a casual test run cannot touch your vault).

```sh
bw login      # first time only
HMB_TEST_BW_SESSION="$(bw unlock --raw)" \
    uv run pytest tests/integration/ -m "integration and bitwarden"
```

Every item the suite creates lives in a dedicated `himitsubako-test-<uuid>` folder that is torn down on test completion, even when a test fails. Your production vault is not touched.

#### macOS Keychain tests

No extra setup. The suite uses a UUID-prefixed service name (`himitsubako-test-<uuid>`) so it cannot collide with real keychain entries, and the fixture's finalizer deletes every key it created.

#### direnv tests

No extra setup beyond having the `direnv` binary on `PATH`. The tests use `direnv allow` / `direnv exec` / `direnv deny` in a throwaway directory — no state is written to your global direnv allow-list and no shell hook is required.

## Code quality

Every commit must pass the full CI gate:

```sh
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest
```

All four are green on every commit to `main`. See `.github/workflows/ci.yml` for the matrix (Python 3.12 and 3.13 on Ubuntu).

## Dependency discipline

himitsubako follows a **pre-install license + health + quarantine gate** for every new package. The rule is that bits on disk are the point of no return — `uv pip install` / `uv add` is the commit to the dependency, not the first `import` statement. Before adding any dependency:

1. **License check.** Fetch the package's LICENSE and compare against `Obsidian/code/allowed-licenses.md` (the project policy). MIT / BSD-3 / Apache-2.0 are Allowed; anything else stops the install and requires an ADR exception. The Bitwarden **SDK** is explicitly disallowed because its license is not OSI-approved — the bitwarden-cli backend shells out to the `bw` binary instead.
2. **Health check.** Score the package against the rubric in `Obsidian/code/oss-health-policy.md` (maintenance cadence, bus factor, security posture, community). Record the result in `Obsidian/code/oss-health-policy-scores.md`.
3. **Quarantine.** Verify the target version was published more than 7 days ago. This defends against the short-window compromised-release attack pattern documented in `Obsidian/code/supply-chain-protection.md`.

"License check owed as a follow-up" is an anti-pattern. Every dependency in `pyproject.toml` has been through this gate. When you bump a version, the gate runs again against the new version's license and publication date.

## Contribution model

At the time of writing, himitsubako is single-maintainer with direct commits to `main`. There is no pull-request process and no code review rotation. If you want to contribute:

1. Open an issue describing the change and its motivation.
2. The maintainer will either pick it up or invite you to send a branch.
3. Accepted contributions go through the same CI gate as everything else.

This is an honest description of the current state, not a permanent model. A contributor-ready process will be documented here when the project starts accepting outside contributions routinely.

## Security issues

Do **not** open a public issue for security vulnerabilities. See [`SECURITY.md`](SECURITY.md) for the disclosure process.

## Releases

Releases are tagged `v<MAJOR>.<MINOR>.<PATCH>`. The release workflow at `.github/workflows/release.yml` triggers on tag push and publishes to PyPI via Trusted Publishers OIDC — no long-lived API tokens. See the workflow file for the full step list. The maintainer's release checklist:

1. Close the sprint. Every planned story landed on `main`, CI is green, docs build clean.
2. Append the `## [X.Y.Z] - YYYY-MM-DD` entry to `CHANGELOG.md`.
3. Bump `pyproject.toml` version and `src/himitsubako/__init__.py` `__version__`.
4. Commit "`chore: release vX.Y.Z`" on `main`.
5. Run `uv run python -m build` locally and `uv run twine check dist/*` as a smoke test.
6. Tag `vX.Y.Z` on that commit and push the tag.
7. Watch the release workflow; approve the `pypi-release` environment gate when prompted.
8. Verify `pip install himitsubako==X.Y.Z` in a scratch venv on a different machine.
