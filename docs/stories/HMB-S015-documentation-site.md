---
type: story
project: himitsubako
id: HMB-S015
status: backlog
sprint: 3
created: 2026-04-10
tags: [himitsubako, docs, mkdocs]
---

# HMB-S015: Documentation Site

## Summary

Build an mkdocs-material documentation site with getting-started guide, backend reference, CLI reference, and pydantic-settings integration guide.

## Motivation

A PyPI library needs documentation beyond the README. mkdocs-material is already declared as a dev dependency in pyproject.toml.

## Acceptance Criteria

- [ ] `docs/` directory with mkdocs source files
- [ ] `mkdocs.yml` configuration for mkdocs-material theme
- [ ] Pages:
  - Getting Started (expanded from README's 60-second section)
  - CLI Reference (`hmb init`, `hmb get`, `hmb set`, `hmb list`, `hmb rotate-key`)
  - Backend Reference (sops, env, keychain, bitwarden-cli, direnv)
  - pydantic-settings Integration
  - Configuration (`.himitsubako.yaml` format, per-credential routing)
  - Why Not ... (expanded comparison section from README)
- [ ] `uv run mkdocs build` succeeds without warnings
- [ ] Stories directory (`docs/stories/`) excluded from the built site

## Dependencies

- All feature stories complete (S001-S012)

## Estimate

2 points
