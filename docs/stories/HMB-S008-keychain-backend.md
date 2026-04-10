---
type: story
project: himitsubako
id: HMB-S008
status: backlog
sprint: 2
created: 2026-04-10
tags: [himitsubako, backend, keychain, keyring, macos]
---

# HMB-S008: macOS Keychain Backend

## Summary

Implement the `keychain` backend using the `keyring` library for OS-native credential storage.

## Motivation

Some credentials (long-lived personal tokens, SSH passphrases) are better stored in the OS keychain than in a git-committed SOPS file. The keychain backend survives repo deletion and does not require any external binary.

## Acceptance Criteria

- [ ] `src/himitsubako/backends/keychain.py` implements `SecretBackend` protocol
- [ ] Uses `keyring` library (optional dependency under `[keychain]` extra)
- [ ] `get(key)` retrieves from keychain using service name derived from project config
- [ ] `set(key, value)` stores in keychain
- [ ] `delete(key)` removes from keychain
- [ ] `list()` is not natively supported by keyring — document this limitation, return empty list or raise informative error
- [ ] Graceful error if `keyring` is not installed (ImportError → clear message pointing to `pip install himitsubako[keychain]`)
- [ ] Unit tests mock `keyring` module; integration tests (marked `@pytest.mark.macos`) hit real keychain
- [ ] 80%+ coverage

## Dependencies

- HMB-S001 (backend protocol)

## Estimate

2 points
