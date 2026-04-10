---
type: story
project: himitsubako
id: HMB-S002
status: backlog
sprint: 1
created: 2026-04-10
tags: [himitsubako, backend, sops, age, encryption]
---

# HMB-S002: SOPS + age Backend

## Summary

Implement the SOPS + age backend: read, write, delete, and list operations against `.secrets.enc.yaml` files via `sops` subprocess calls.

## Motivation

SOPS + age is the primary backend and the opinionated default. All other backends are escape hatches. This backend must be solid before the CLI or Python API can be useful.

## Acceptance Criteria

- [ ] `src/himitsubako/backends/sops.py` implements `SecretBackend` protocol
- [ ] `get(key)` decrypts and returns a single value from the encrypted YAML file
- [ ] `set(key, value)` encrypts and writes a key-value pair to the encrypted YAML file
- [ ] `delete(key)` removes a key from the encrypted YAML file and re-encrypts
- [ ] `list()` returns all key names from the encrypted YAML file (decrypts to read keys)
- [ ] Subprocess calls to `sops` handle missing binary, missing key file, and decryption failure with clear error messages
- [ ] Unit tests mock subprocess calls; integration tests (marked `@pytest.mark.integration`) require `sops` and `age` on PATH
- [ ] 80%+ coverage

## Dependencies

- HMB-S001 (backend protocol, error types)

## Estimate

3 points
