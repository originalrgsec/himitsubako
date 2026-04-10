---
type: story
project: himitsubako
id: HMB-S013
status: backlog
sprint: 3
created: 2026-04-10
tags: [himitsubako, testing, integration]
---

# HMB-S013: Integration Tests for All Backends

## Summary

Write integration tests that exercise each backend against real external dependencies (SOPS+age binaries, macOS Keychain, Bitwarden CLI, direnv).

## Motivation

Unit tests with mocked subprocesses prove the logic works. Integration tests prove the library actually interacts correctly with real tools. Both are required before a v0.1.0 release.

## Acceptance Criteria

- [ ] Integration test suite in `tests/integration/`
- [ ] SOPS backend: full round-trip (init, set, get, list, delete, rotate-key) with real `sops` and `age`
- [ ] Keychain backend: full round-trip on macOS (marked `@pytest.mark.macos`)
- [ ] Bitwarden CLI backend: full round-trip with real `bw` (marked `@pytest.mark.integration`, requires unlocked vault)
- [ ] Env backend: verify prefix filtering against real `os.environ`
- [ ] direnv helper: verify generated `.envrc` actually works with `direnv exec`
- [ ] CLI integration: `hmb init` → `hmb set` → `hmb get` → `hmb list` end-to-end flow
- [ ] Per-credential routing: mixed-backend config with real backends
- [ ] Tests are skippable via markers when external dependencies are unavailable
- [ ] CI can run the subset that only needs `sops` and `age` (installable via GitHub Actions)

## Dependencies

- All backend stories (HMB-S002, S007, S008, S009, S010)
- HMB-S012 (per-credential routing)

## Estimate

3 points
