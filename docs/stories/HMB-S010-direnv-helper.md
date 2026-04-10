---
type: story
project: himitsubako
id: HMB-S010
status: backlog
sprint: 2
created: 2026-04-10
tags: [himitsubako, direnv, envrc, shell]
---

# HMB-S010: direnv Helper

## Summary

Implement the direnv integration that generates and updates `.envrc` files to auto-load SOPS-decrypted secrets when entering a project directory.

## Motivation

The "zero import" experience — secrets available as plain env vars via `os.environ` — depends on direnv loading them on `cd`. The helper generates a correct `.envrc` and keeps it in sync when secrets are added or removed.

## Acceptance Criteria

- [ ] `src/himitsubako/direnv.py` with `generate_envrc()` and `update_envrc()` functions
- [ ] `generate_envrc()` creates an `.envrc` that runs `sops -d .secrets.enc.yaml` and exports each key
- [ ] `update_envrc()` reads the current `.envrc`, preserves user-added lines, and updates the himitsubako-managed section (delimited by comments)
- [ ] `hmb init` calls `generate_envrc()` (integrates with HMB-S003)
- [ ] `hmb set` calls `update_envrc()` after writing a new secret (integrates with HMB-S004)
- [ ] Handles missing `direnv` binary gracefully (generates file but warns that `direnv` is not installed)
- [ ] Unit tests, 80%+ coverage

## Dependencies

- HMB-S001 (config)
- HMB-S002 (SOPS backend, for the decryption command in `.envrc`)

## Estimate

2 points
