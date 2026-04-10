---
type: story
project: himitsubako
id: HMB-S007
status: backlog
sprint: 2
created: 2026-04-10
tags: [himitsubako, backend, env, environment-variables]
---

# HMB-S007: Environment Variable Backend

## Summary

Implement the `env` backend that reads and lists credentials from `os.environ`.

## Motivation

The `env` backend is the zero-dependency escape hatch for CI/CD pipelines, containers, and 12-factor deployments. It is also the implicit fallback when no config file is found.

## Acceptance Criteria

- [ ] `src/himitsubako/backends/env.py` implements `SecretBackend` protocol
- [ ] `get(key)` returns `os.environ[key]`, raises `SecretNotFoundError` if missing
- [ ] `set(key, value)` raises `BackendError` — env backend is read-only (env vars are set externally)
- [ ] `delete(key)` raises `BackendError` — env backend is read-only
- [ ] `list()` returns all env var names (optionally filtered by prefix configured in `.himitsubako.yaml`)
- [ ] Prefix filtering: if `env_prefix: "MYAPP_"` is configured, `list()` only returns keys starting with that prefix and `get("KEY")` resolves to `os.environ["MYAPP_KEY"]`
- [ ] Unit tests, 80%+ coverage

## Dependencies

- HMB-S001 (backend protocol)

## Estimate

1 point
