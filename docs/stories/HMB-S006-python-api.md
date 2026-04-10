---
type: story
project: himitsubako
id: HMB-S006
status: backlog
sprint: 1
created: 2026-04-10
tags: [himitsubako, api, python]
---

# HMB-S006: Python API with Config-Driven Backend Resolution

## Summary

Implement the top-level `himitsubako.get()` and `himitsubako.set()` functions that resolve the correct backend per credential based on `.himitsubako.yaml` configuration.

## Motivation

The Python API is what other projects import. It must be simple (`from himitsubako import get; key = get("MY_KEY")`) while supporting per-credential backend routing under the hood.

## Acceptance Criteria

- [ ] `himitsubako.get(key)` resolves backend from config and returns the decrypted value
- [ ] `himitsubako.set(key, value)` resolves backend from config and stores the value
- [ ] Config resolution: walks up from cwd to find `.himitsubako.yaml`, falls back to defaults
- [ ] Default backend is `sops` if `.himitsubako.yaml` not found but `.sops.yaml` exists
- [ ] Falls back to `env` backend if no config files found (reads `os.environ`)
- [ ] `himitsubako.list_secrets()` returns all keys from the resolved backend
- [ ] `himitsubako.get_backend(name)` returns a specific backend instance for advanced use
- [ ] All public API functions are importable from `himitsubako` top-level
- [ ] Unit tests for config resolution, backend dispatch, and fallback behavior
- [ ] 80%+ coverage

## Dependencies

- HMB-S001 (config, protocol, errors)
- HMB-S002 (SOPS backend, used as default)

## Estimate

3 points
