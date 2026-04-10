---
type: story
project: himitsubako
id: HMB-S004
status: backlog
sprint: 1
created: 2026-04-10
tags: [himitsubako, cli, get, set, list]
---

# HMB-S004: `hmb get` / `hmb set` / `hmb list` CLI Commands

## Summary

Implement the core secret management CLI commands: `hmb get <key>`, `hmb set <key>` (prompts for value with masked input), and `hmb list`.

## Motivation

These are the daily-driver commands. A developer adds secrets with `hmb set`, reads them with `hmb get`, and audits what exists with `hmb list`.

## Acceptance Criteria

- [ ] `hmb get <key>` prints the decrypted value to stdout (for piping) or rich-formatted to terminal
- [ ] `hmb get <key>` exits non-zero with clear message if key not found
- [ ] `hmb set <key>` prompts for value with masked input (click.prompt with hide_input=True)
- [ ] `hmb set <key> --value <val>` accepts value as argument for scripting (with warning about shell history)
- [ ] `hmb list` prints all key names (not values) in the configured secrets file
- [ ] All commands respect `.himitsubako.yaml` for backend selection
- [ ] Exit codes: 0 success, 1 runtime error, 2 usage error
- [ ] Unit tests for each command path
- [ ] 80%+ coverage

## Dependencies

- HMB-S001 (config, errors)
- HMB-S002 (SOPS backend)

## Estimate

2 points
