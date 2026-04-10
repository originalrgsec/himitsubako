---
type: story
project: himitsubako
id: HMB-S003
status: backlog
sprint: 1
created: 2026-04-10
tags: [himitsubako, cli, init, scaffolding]
---

# HMB-S003: `hmb init` CLI Command

## Summary

Implement the `hmb init` command that scaffolds a project for himitsubako: creates an age keypair (if needed), writes `.sops.yaml`, generates `.envrc`, encrypts an empty `.secrets.enc.yaml`, and writes `.himitsubako.yaml`.

## Motivation

The primary value proposition of himitsubako over raw SOPS is opinionated scaffolding. `hmb init` wires everything up correctly the first time so the developer never has to remember the SOPS config format, age key paths, or direnv syntax.

## Acceptance Criteria

- [ ] `hmb init` creates age keypair at `~/.config/sops/age/keys.txt` if it does not exist (prompts before overwriting if it does)
- [ ] Writes `.sops.yaml` with the user's age public key as recipient
- [ ] Creates empty `.secrets.enc.yaml` encrypted with the age key
- [ ] Generates `.envrc` that sources decrypted secrets via `sops -d`
- [ ] Writes `.himitsubako.yaml` with sops as the default backend
- [ ] Adds `.secrets.enc.yaml` to `.gitignore` if not already present (wait — encrypted file IS committed; ensure `.envrc` and decrypted files are gitignored instead)
- [ ] Idempotent: re-running `hmb init` does not overwrite existing files without `--force`
- [ ] Unit tests cover all file generation paths
- [ ] 80%+ coverage

## Dependencies

- HMB-S001 (config model, error types)
- HMB-S002 (SOPS backend for encrypting the empty secrets file)

## Estimate

3 points
