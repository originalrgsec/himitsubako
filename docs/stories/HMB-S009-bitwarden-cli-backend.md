---
type: story
project: himitsubako
id: HMB-S009
status: backlog
sprint: 2
created: 2026-04-10
tags: [himitsubako, backend, bitwarden, cli]
---

# HMB-S009: Bitwarden CLI Backend

## Summary

Implement the `bitwarden-cli` backend that reads credentials from a Bitwarden vault via the `bw` CLI (GPL-3.0 licensed, invoked as subprocess).

## Motivation

Developers already using Bitwarden for password management want their dev credentials in the same vault. The `bw` CLI is GPL-3.0 and safe to invoke via subprocess without license contamination of this MIT-licensed library.

## Acceptance Criteria

- [ ] `src/himitsubako/backends/bitwarden.py` implements `SecretBackend` protocol
- [ ] `get(key)` runs `bw get item <key>` or equivalent, parses JSON output for the credential value
- [ ] `set(key, value)` creates or updates a Bitwarden item via `bw create` / `bw edit`
- [ ] `delete(key)` removes the item via `bw delete`
- [ ] `list()` returns item names from the configured Bitwarden folder/collection
- [ ] Handles `bw` session management: checks `BW_SESSION` env var, prompts for unlock if needed
- [ ] Clear error messages for: `bw` not on PATH, vault locked, item not found
- [ ] Unit tests mock subprocess; integration tests (marked `@pytest.mark.integration`) require `bw` CLI and unlocked vault
- [ ] 80%+ coverage

## Dependencies

- HMB-S001 (backend protocol)

## Estimate

3 points
