# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-dev.1] - 2026-04-10

Sprint 1: Foundation + SOPS Backend.

### Added

- `SecretBackend` protocol — runtime-checkable structural typing contract for all backends
- `HimitsubakoConfig` pydantic model with frozen sub-configs (sops, keychain, bitwarden, env)
- `find_config()` walks up directory tree to locate `.himitsubako.yaml`
- `load_config()` with YAML parsing and validation
- Error hierarchy: `HimitsubakoError` > `BackendError` > `SecretNotFoundError`, `ConfigError`
- SOPS+age backend: get/set/delete/list via `sops` subprocess, atomic writes via tmpfile+rename
- `hmb init` — creates age keypair, `.sops.yaml`, `.envrc`, `.secrets.enc.yaml`, `.himitsubako.yaml`; idempotent with `--force` override
- `hmb get <key>` — prints decrypted value to stdout
- `hmb set <key>` — masked prompt or `--value` flag for scripting
- `hmb list` — prints all key names
- `hmb rotate-key --new-key <path>` — updates `.sops.yaml` and re-encrypts via `sops updatekeys`; `--dry-run` mode
- Python API: `himitsubako.get()`, `set_secret()`, `list_secrets()` with config-driven backend resolution
- Env-var fallback when no config files found (read-only)
- 16 story files in `docs/stories/` covering the full v0.1.0 roadmap (3 sprints)

### Security

- Secret key names excluded from error messages to prevent leakage in logs/tracebacks
- Broad `except` in config loading narrowed to `ValueError | TypeError`
- `types-PyYAML` added for static analysis confidence on YAML parsing paths

[0.1.0-dev.1]: https://github.com/originalrgsec/himitsubako/commits/v0.1.0-dev.1
