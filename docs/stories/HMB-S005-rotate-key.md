---
type: story
project: himitsubako
id: HMB-S005
status: backlog
sprint: 1
created: 2026-04-10
tags: [himitsubako, cli, rotation, security]
---

# HMB-S005: `hmb rotate-key`

## Summary

Implement the `hmb rotate-key` command that re-encrypts all configured secrets files with a new age key.

## Motivation

Key rotation is a security hygiene requirement. When an age key is compromised or as part of periodic rotation, the developer needs a single command that re-encrypts every secrets file across all configured projects without manual SOPS invocations.

## Acceptance Criteria

- [ ] `hmb rotate-key --new-key <path>` re-encrypts `.secrets.enc.yaml` with the new age key
- [ ] Updates `.sops.yaml` to reference the new public key
- [ ] Validates the new key file exists and is a valid age key before starting
- [ ] Atomic operation: if re-encryption fails mid-way, the original file is preserved
- [ ] Supports `--projects <dir1> <dir2>` to rotate across multiple project directories
- [ ] Dry-run mode (`--dry-run`) that lists what would change without modifying files
- [ ] Unit tests with mocked subprocess; integration test with real sops/age
- [ ] 80%+ coverage

## Dependencies

- HMB-S001 (config, errors)
- HMB-S002 (SOPS backend)

## Estimate

3 points
