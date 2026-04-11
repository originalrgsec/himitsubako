# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-04-11

Sprint 3 closes himitsubako's path to PyPI. Seven stories land together:
the CRUD closeout (`hmb delete`, `hmb status`), a real integration test
suite that surfaced and fixed a latent SOPS encryption bug that had
broken every `hmb set` since v0.1.0, a CI pipeline with SHA-pinned
actions and verified `sops`+`age` binaries, a full mkdocs-material
documentation site, local-only integration tests for keychain / bw /
direnv, and the release workflow + Trusted Publishers OIDC binding
that publishes to PyPI on every `v*.*.*` tag.

### Added — CLI commands

- **HMB-S018 — `hmb delete` CLI command.** Removes a secret from the
  configured backend with a confirmation prompt (`--force` / `--yes`
  to skip, `--missing-ok` for idempotent cleanup). Routed dispatch
  names the resolved target backend in the prompt rather than the
  router wrapper. Exit codes: `0` success, `1` not found, `2` backend
  error (env backend read-only, keychain denied, etc.).

- **HMB-S019 — `hmb status` diagnostic command.** Read-only
  introspection of the active configuration: config path, default
  backend, SOPS binary + age recipients from `.sops.yaml`, the
  `BackendRouter` table in declaration order, and a per-backend
  ping-style availability check. `--json` emits a single JSON object
  for scripting. Never reads, writes, or enumerates any credential.
  Also adds a public `KeychainBackend.check_availability()` method.

### Added — testing and infrastructure

- **HMB-S013 — CI-runnable integration test suite.** New
  `tests/integration/` tree with 26 real-binary tests for SOPS and env
  backends, `BackendRouter` dispatch, and the full
  `hmb init → set → get → list → delete → status` CLI flow. Excluded
  from the default `uv run pytest` via `--ignore=tests/integration`;
  run explicitly with `uv run pytest tests/integration/`.

- **HMB-S014 — GitHub Actions CI pipeline.**
  `.github/workflows/ci.yml` runs ruff check, ruff format check, mypy,
  unit tests with a `--cov-fail-under=80` gate, and the S013
  integration subset on every push to `main` and every PR. Matrix:
  Python 3.12 and 3.13 on `ubuntu-latest`. Every `uses:` reference is
  SHA-pinned; `sops` v3.12.2 and `age` v1.3.1 are installed from
  upstream releases with SHA256 verification. Top-level
  `permissions: contents: read`, concurrency group cancels stale
  runs, no repo secrets consumed.

- **HMB-S020 — local-only integration tests.** New test modules for
  the backends that cannot run in default CI: `test_keychain_real.py`
  (macOS login keychain with UUID-prefixed service and finalizer
  teardown), `test_bitwarden_real.py` (gated on an explicit
  `HMB_TEST_BW_SESSION` env var with per-test folder isolation), and
  `test_direnv_real.py` (real `direnv allow`/`exec`/`deny` isolation,
  covering duplicate-marker refusal and shlex-quoted tricky filenames
  end-to-end). 14 new tests total.

### Added — release infrastructure

- **HMB-S016 — PyPI publish preparation.** `pyproject.toml` version
  bumped to `0.3.0`; `src/himitsubako/__init__.py` `__version__`
  matches. `project.urls` now declares Documentation and Changelog
  URLs. New `CONTRIBUTING.md` (development setup, running unit vs
  integration tests, dependency license discipline, release
  checklist) and `SECURITY.md` (supported versions, private
  vulnerability reporting via GitHub Security Advisories, in-scope
  and out-of-scope boundaries, regression-guarded defense list). New
  `.github/workflows/release.yml` triggered on final `v*.*.*` tags:
  verify → build → publish jobs. Publish uses Trusted Publishers
  OIDC (`pypa/gh-action-pypi-publish@v1.13.0`, SHA-pinned) bound to
  the `pypi-release` GitHub Actions environment with a required-
  reviewer approval gate. No long-lived PyPI API tokens. A build-job
  guard asserts that the git tag, `pyproject.toml` version, and
  `himitsubako.__version__` all agree before any artifact is
  produced. Local smoke test before this commit: wheel and sdist
  built via `python -m build`, `twine check dist/*` PASSED, scratch
  venv install of the wheel reports `hmb, version 0.3.0`.

### Docs

- **HMB-S015 — mkdocs-material documentation site.** New `docs/` tree
  plus top-level `mkdocs.yml` configuring the `material` theme with a
  light/dark palette toggle and tabbed navigation. Pages: landing,
  getting-started walkthrough, full CLI reference, configuration and
  `BackendRouter` guide, one backend page each for SOPS / env /
  keychain / bitwarden-cli, integration pages for pydantic-settings
  and direnv, a user-facing security summary, a "why not ..." section,
  and a changelog page that renders `CHANGELOG.md` via the snippets
  extension. `uv run mkdocs build --strict` is green in 0.3 s. Deploy
  target intentionally deferred — the build is the success criterion;
  GitHub Pages / Read the Docs / Cloudflare Pages selection is a
  follow-up decision.

### Fixed

- **HMB-S013 (discovered by new integration tests) —
  `SopsBackend._encrypt` could not encrypt against a default-init'd
  vault.** The backend writes to a `tempfile.mkstemp(suffix=".yaml")`
  tempfile and then calls `sops --encrypt --in-place <tmpfile>`.
  sops applies `.sops.yaml`'s `creation_rules` `path_regex` against
  the file it's operating on — which is the tempfile name, not
  `.secrets.enc.yaml` — so sops aborts with `error loading config:
  no matching creation rules found`. This broke every `hmb set` /
  `hmb delete` / rotate path in v0.1.0 through v0.2.0; unit tests
  did not catch it because subprocess was mocked. The fix passes
  `--filename-override <real_secrets_file>` so sops applies the
  creation_rules against the real target path. Requires
  **sops >= 3.8.0** (the version that introduced `--filename-override`);
  the README and backend table now document the minimum. A unit
  regression test in `TestSopsBackendFilenameOverride` pins argv
  ordering so the flag cannot silently drop.

### Chore

- Codebase-wide `ruff format` pass so the CI format-check stays green.
- mypy strict pass over `src/`; one pre-existing type narrowing in
  `cli/secrets.py::list_secrets` annotated as `SecretBackend | None`.
- Register `bitwarden` and `direnv` pytest markers to support the
  S020 opt-in local-only suites and the S014 CI filter.

## [0.2.0] - 2026-04-11

Sprint 2 ships the alternate-backend track and the per-credential
routing dispatcher that ties them together. v0.2.0 turns himitsubako
from "a SOPS wrapper" into "a multi-backend credential abstraction"
without breaking any v0.1.x configuration.

### Added — backends

- **HMB-S007 — first-class environment variable backend.** `EnvBackend(prefix: str = "")`
  in `himitsubako.backends.env`. Read-only by design (`set`/`delete`
  raise `BackendError`). With a configured prefix, `get("DB_PASSWORD")`
  resolves `MYAPP_DB_PASSWORD` and `list_keys()` returns matching
  variables with the prefix stripped. The internal `_EnvFallbackBackend`
  shim is removed; no-config fallback now returns the real `EnvBackend()`.
  `hmb list` against an unprefixed env backend emits a stderr warning
  so users do not mistake inherited shell credentials for app secrets.

- **HMB-S008 — macOS Keychain backend.** `KeychainBackend(service: str)`
  in `himitsubako.backends.keychain`. Wraps the `keyring` library
  (optional `[keychain]` extra). `list_keys()` raises `BackendError`
  unconditionally because the keyring API does not expose enumeration —
  the CLI catches this and prints a friendly "this backend does not
  support listing" message. Insecure-backend deny-list at first call:
  the resolved `keyring.get_keyring()` is rejected if its **MRO** matches
  `Null`, `PlaintextKeyring`, `EncryptedKeyring`, or `fail.Keyring`,
  preventing both direct and subclass-based bypass on misconfigured
  Linux hosts.

- **HMB-S009 — Bitwarden CLI subprocess backend.** `BitwardenBackend(folder, bin, unlock_command)`
  in `himitsubako.backends.bitwarden`. Invokes the `bw` system binary;
  no `bitwarden-sdk` Python dependency (the SDK is non-OSI; see the
  COR-S037 retrospective). Three modes:
  - **Strict (default):** `BW_SESSION` must be set; the library never
    prompts. Missing/empty session raises a clear `BackendError`.
  - **Pinned bin:** `bin=` constructor arg or `HIMITSUBAKO_BW_BIN` env
    var pins an absolute path, mitigating T-005 (PATH hijack of `bw`).
  - **Shell-out unlock:** `unlock_command` runs a configured command,
    captures stdout as the master password, pipes it to `bw unlock --raw`
    via `BW_PASSWORD` env var (NOT argv) to obtain a session token used
    in-memory only. Token is never written to disk or logged.
  Hardened secrecy: `BW_SESSION` is never logged or interpolated into
  errors; the `_raise_friendly` helper redacts any base64 token-like
  string from `bw` stderr before re-raising. All subprocess calls use
  a 30s timeout matching SOPS.

### Added — dispatcher

- **HMB-S012 — `BackendRouter` per-credential routing.** New
  `himitsubako.router.BackendRouter` implements `SecretBackend` and
  dispatches each key to the configured backend. Resolution order:
  exact match in `config.credentials` → first matching glob (declaration
  order, `fnmatch.fnmatchcase`) → `default_backend`. `list_keys()`
  aggregates across all backends in use; backends that raise on
  `list_keys` (keychain) are caught, logged to stderr as a partial-
  failure warning, and skipped. Backend instances are cached on first
  construction. Both `cli/secrets.py` and `api.py` were refactored to
  return a router rather than a single backend, so all CLI commands and
  Python API calls transparently support per-credential routing.

  **Backward compatibility:** configs with no `credentials:` section
  behave identically to v0.1.x. All v0.1.x tests pass unchanged.

### Added — integrations

- **HMB-S010 — direnv helper.** New `himitsubako.direnv` module with
  `generate_envrc()` and `update_envrc()`. The managed block is
  delimited by `# --- himitsubako start ---` and `# --- himitsubako end ---`
  markers; `update_envrc` preserves any user lines outside the markers
  and replaces the managed block in place. Idempotent. Refuses to
  operate on a `.envrc` with duplicate markers (would silently corrupt
  user lines between blocks). The `secrets_file` path is `shlex.quote`d
  before interpolation into the eval line so paths with spaces or shell
  metacharacters cannot break the eval. New `hmb direnv-export` CLI
  command regenerates the managed block on demand. `hmb init` uses the
  new helper for the initial `.envrc`; `hmb set` calls `update_envrc()`
  best-effort after a successful sops write.

- **HMB-S011 — pydantic-settings source.** `HimitsubakoSettingsSource`
  in `himitsubako.pydantic` extends `PydanticBaseSettingsSource` to
  pull each settings field from a himitsubako backend or router. Use
  in `settings_customise_sources` to mix backends in a single settings
  model — `db_password` from SOPS, `oauth_client_secret` from Keychain,
  routed by `.himitsubako.yaml`. Recommended source order documented
  in the module: `init kwargs > env > himitsubako > dotenv > file_secret > defaults`.
  Optional `[pydantic-settings]` extra; ImportError converts to a clear
  BackendError naming the install command.

### Config schema additions

- `HimitsubakoConfig.credentials: dict[str, CredentialRoute]` — new
  optional section for per-credential routing.
- `BitwardenConfig.bin: str | None` and `BitwardenConfig.unlock_command: str | None`
  — for HMB-S009.
- `extra=forbid` on `CredentialRoute` rejects unknown fields.

### Security

- **T-005 mitigated** (HMB-S009): `bw` binary path can be pinned via
  `HIMITSUBAKO_BW_BIN` or config to prevent PATH hijack.
- **T-007 partially mitigated** (HMB-S009): `BW_SESSION` is never logged
  or interpolated into error strings; `bw` stderr is sanitized to redact
  base64 token-like substrings before re-raising. The OS-level
  visibility of env vars to same-user processes remains an accepted
  limitation of the env-var session model.
- **T-008 mitigated** (HMB-S009): 30-second subprocess timeout on all
  `bw` calls, matching the SOPS pattern from v0.1.1.
- **T-020 mitigated** (HMB-S008): Keychain access delegates to the OS
  via the keyring library; first access from a new binary triggers a
  Touch ID / password prompt on macOS.
- **T-022 mitigated via M-014** (HMB-S009): Documentation guidance on
  safe `unlock_command` choices; the library does not log unlock_command
  output.
- **T-023 mitigated via M-015** (HMB-S008): Insecure-backend deny-list
  at first call, with MRO-based subclass detection.

### Test state

- 80 → 156 passing tests (+76, +95%)
- Coverage 86.27% → 84% (broader surface, same density)
- ruff clean
- Code review (python-reviewer): 2 CRITICAL + 4 HIGH findings, all
  fixed before tag. Findings included BW_SESSION leak via stderr
  passthrough (now redacted), BW_PASSWORD env var defense-in-depth
  cleanup, keychain MRO bypass (now MRO-checked), direnv duplicate
  markers (now refused), direnv shlex injection (now quoted).

[0.2.0]: https://github.com/originalrgsec/himitsubako/commits/v0.2.0

## [0.1.1] - 2026-04-11

Hardening release. Closes the four known limitations flagged at v0.1.0 ship time
(threat-model items T-001, T-004, T-010, T-018; ADR open question OQ-4).
No new public surface beyond the additions listed below; v0.2.0 alternate
backends still land in the next sprint.

### Added

- `SopsBackend(secrets_file, sops_bin=None)` — new optional `sops_bin` argument
  pins the `sops` binary path instead of relying on PATH lookup.
- `HIMITSUBAKO_SOPS_BIN` environment variable — when set and non-empty, takes
  precedence over both the constructor argument and the config field.
- `sops.bin` field in `.himitsubako.yaml` — optional path to a non-PATH `sops`
  binary, plumbed through both the CLI (`hmb get/set/list/rotate-key`) and the
  Python API. Defaults to `None`, preserving v0.1.0 behavior.
- `hmb get KEY --reveal` (`-r`) — boolean flag that authorizes printing the
  decrypted value to a TTY. When stdout is a pipe or redirect, the flag is
  optional and the value is printed as before, so `$(hmb get KEY)` and
  `hmb get KEY | pbcopy` continue to work unchanged.

### Changed

- All `subprocess.run` calls in `SopsBackend` now pass `timeout=30s` (hardcoded
  module constant `_SOPS_TIMEOUT_SECONDS`). Timeouts are caught and re-raised
  as `BackendError("sops", "sops <decrypt|encrypt> timed out after 30s")`.
- `SopsBackend._encrypt` writes the temp plaintext file with mode `0o600` from
  creation (via `os.fchmod`), and re-asserts `0o600` on the destination file
  after the atomic rename. The destination mode is now independent of the
  caller's umask.
- `hmb get KEY` running against a TTY without `--reveal` exits 1 with a stderr
  message pointing at the flag. This is a deliberate behavior change from
  v0.1.0; scripts that piped output are unaffected.

### Security

- **T-001 mitigated.** A malicious `sops` binary earlier in PATH can no longer
  silently shadow the intended one; operators can pin an absolute path via
  env var or config.
- **T-004 mitigated.** A hung or hostile `sops` subprocess can no longer block
  himitsubako indefinitely; the 30-second timeout caps the worst case.
- **T-010 mitigated.** `.secrets.enc.yaml` is now mode `0600` regardless of
  umask, narrowing the local-disclosure window on multi-user systems.
- **T-018 mitigated.** `hmb get` no longer prints plaintext to a terminal by
  default. Shoulder-surfing and terminal scrollback exposure now require an
  explicit `--reveal` opt-in per invocation.
- ADR open question **OQ-4 closed**: TTY-aware reveal gate selected over
  config-driven defaults to keep script ergonomics intact while protecting
  interactive sessions.

[0.1.1]: https://github.com/originalrgsec/himitsubako/commits/v0.1.1

## [0.1.0] - 2026-04-11

First rescoped release: the SOPS track ships standalone.

v0.1.0 was originally planned as the full multi-backend release (SOPS, macOS Keychain, Bitwarden CLI, env, direnv, pydantic-settings source, docs site, PyPI publish). After Sprint 1 shipped the SOPS track end-to-end, the version was rescoped down to "SOPS works standalone" so that later multi-backend work lands in v0.2.0 and the public PyPI release lands in v0.3.0. See the project PRD for the new phasing.

This is not yet on PyPI. The public release target is v0.3.0 (HMB-S016).

### Added

- `SecretBackend` protocol — `@runtime_checkable` structural typing contract with `get`, `set`, `delete`, `list_keys`, and a `backend_name` property. No `rotate` method in the protocol; credential-level rotation is `set(key, new_value)` and age-key rotation is the `hmb rotate-key` CLI command.
- `HimitsubakoConfig` pydantic model with frozen sub-configs (`SopsConfig`, `KeychainConfig`, `BitwardenConfig`, `EnvConfig`). v0.1.0 only routes the `sops` backend; other `default_backend` values parse but fail fast at CLI dispatch.
- `find_config()` walks up the directory tree to locate `.himitsubako.yaml`.
- `load_config()` parses YAML via `yaml.safe_load` and wraps all errors in `ConfigError`.
- Error hierarchy: `HimitsubakoError > BackendError > SecretNotFoundError`, plus `ConfigError`.
- SOPS + age backend: `get`, `set`, `delete`, `list_keys` via `sops` subprocess; atomic writes via tempfile-plus-rename inlined in the backend.
- `hmb init` — creates an age keypair (via `age-keygen`) if absent, writes `.sops.yaml`, `.envrc`, `.secrets.enc.yaml` (SOPS-encrypted empty file), and `.himitsubako.yaml`. Idempotent; `--force` to overwrite.
- `hmb get <key>` — prints the decrypted value to stdout. Exits 1 with a message to stderr if the key is not found.
- `hmb set <key>` — masked prompt by default; `--value <v>` for scripting.
- `hmb list` — prints all key names managed by the configured backend.
- `hmb rotate-key --new-key <path>` — updates `.sops.yaml` recipients and re-encrypts the project's SOPS file via `sops updatekeys`. `--dry-run` prints the plan without executing.
- Python API: `himitsubako.get()`, `set_secret()`, `list_secrets()` with config-driven backend resolution. Fallback chain: `.himitsubako.yaml` > `.sops.yaml` > read-only env var fallback.
- 16 story files in `docs/stories/` covering the v0.1.0 → v0.3.0 roadmap (Sprint 1 through Sprint 3).

### Security

- `SecretNotFoundError` excludes credential key names from its string representation; the missing key is still accessible programmatically via `err.key`.
- Broad `except` in config loading narrowed to `ValueError | TypeError`.
- `types-PyYAML` added for static analysis confidence on YAML parsing paths.
- SOPS backend tests assert that credential values do not appear in captured output.
- `hmb set` masks prompted input via `click.prompt(hide_input=True)`.
- `yaml.safe_load()` used exclusively (no `yaml.load` or `yaml.unsafe_load`).

### Known Limitations (v0.1.1 hardening targets)

- `hmb get` prints the full plaintext value to stdout with no `--reveal` gate. Redacted-by-default output is the top v0.1.1 priority.
- `.secrets.enc.yaml` is written with the default umask (usually 0644) rather than an explicit 0600 chmod.
- The SOPS backend resolves `sops` via PATH only and does not set a subprocess timeout.

### Deferred

| Feature | Deferred to | Story |
|---|---|---|
| First-class env backend (CLI-routable) | v0.2.0 | HMB-S007 |
| macOS Keychain backend | v0.2.0 | HMB-S008 |
| Bitwarden CLI backend | v0.2.0 | HMB-S009 |
| direnv integration helper | v0.2.0 | HMB-S010 |
| pydantic-settings source | v0.2.0 | HMB-S011 |
| Per-credential backend routing | v0.3.0 | HMB-S012 |
| Real-binary integration tests | v0.3.0 | HMB-S013 |
| CI pipeline (GitHub Actions) | v0.3.0 | HMB-S014 |
| mkdocs documentation site | v0.3.0 | HMB-S015 |
| PyPI publication | v0.3.0 | HMB-S016 |

[0.1.0]: https://github.com/originalrgsec/himitsubako/commits/v0.1.0
