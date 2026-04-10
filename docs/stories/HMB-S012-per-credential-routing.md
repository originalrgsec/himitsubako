---
type: story
project: himitsubako
id: HMB-S012
status: backlog
sprint: 3
created: 2026-04-10
tags: [himitsubako, config, routing, multi-backend]
---

# HMB-S012: Per-Credential Backend Routing

## Summary

Implement per-credential backend routing in `.himitsubako.yaml` so different secrets can live in different backends, all accessed through the same `himitsubako.get()` call.

## Motivation

The README promises that "`devto_api_key` can live in SOPS while `aws_access_key_id` lives in macOS Keychain." This story delivers that capability by extending the config model to support credential-level backend overrides.

## Acceptance Criteria

- [ ] `.himitsubako.yaml` supports a `credentials` section mapping key names or patterns to backends
- [ ] Example config:
  ```yaml
  default_backend: sops
  credentials:
    aws_access_key_id:
      backend: keychain
    aws_secret_access_key:
      backend: keychain
    "ghcr_*":
      backend: env
  ```
- [ ] Glob pattern matching for credential names (e.g., `ghcr_*` matches `ghcr_token`, `ghcr_username`)
- [ ] `himitsubako.get(key)` resolves the correct backend per the routing config
- [ ] `himitsubako.list_secrets()` aggregates across all configured backends
- [ ] Config validation: reject unknown backend names, warn on overlapping patterns
- [ ] Unit tests for routing resolution, pattern matching, aggregated listing
- [ ] 80%+ coverage

## Dependencies

- HMB-S006 (Python API)
- HMB-S007, HMB-S008 (alternate backends to route to)

## Estimate

3 points
