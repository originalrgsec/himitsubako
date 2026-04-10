---
type: story
project: himitsubako
id: HMB-S001
status: backlog
sprint: 1
created: 2026-04-10
tags: [himitsubako, scaffolding, foundation]
---

# HMB-S001: Project Scaffolding

## Summary

Create the `src/himitsubako/` package structure, `tests/` directory, backend protocol (abstract base class), configuration model (`HimitsubakoConfig`), and error type hierarchy.

## Motivation

Every subsequent story depends on the package skeleton, the backend protocol contract, and the config model. This story establishes the foundation that all backends and the CLI build on.

## Acceptance Criteria

- [ ] `src/himitsubako/__init__.py` exists with version string
- [ ] `src/himitsubako/backends/` package with `protocol.py` defining `SecretBackend` abstract base class (get, set, delete, list operations)
- [ ] `src/himitsubako/config.py` with `HimitsubakoConfig` pydantic model parsing `.himitsubako.yaml`
- [ ] `src/himitsubako/errors.py` with error hierarchy: `HimitsubakoError` base, `BackendError`, `ConfigError`, `SecretNotFoundError`
- [ ] `tests/` directory with `conftest.py` and at least one test per module
- [ ] `uv sync` succeeds, `uv run pytest` passes, `uv run ruff check src/ tests/` clean
- [ ] 80%+ coverage on all new code

## Estimate

2 points
