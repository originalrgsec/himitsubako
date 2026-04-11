# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
