---
type: story
project: himitsubako
id: HMB-S011
status: backlog
sprint: 2
created: 2026-04-10
tags: [himitsubako, pydantic, pydantic-settings, integration]
---

# HMB-S011: pydantic-settings Source

## Summary

Implement `HimitsubakoSettingsSource` as a custom `pydantic-settings` source that pulls credentials from himitsubako backends.

## Motivation

Python applications using `pydantic-settings` for configuration can declaratively load credentials from himitsubako without manual `get()` calls. This is the cleanest integration path for structured applications.

## Acceptance Criteria

- [ ] `src/himitsubako/pydantic.py` with `HimitsubakoSettingsSource` class
- [ ] Implements `pydantic-settings` `PydanticBaseSettingsSource` interface
- [ ] For each field in the settings model, attempts `himitsubako.get(field_name)` using the resolved backend
- [ ] Falls through gracefully (returns empty dict for missing keys) so other sources can provide values
- [ ] Works with the `settings_customise_sources` classmethod as documented in README
- [ ] Optional dependency under `[pydantic-settings]` extra; clear ImportError message if not installed
- [ ] Unit tests with mock backends; integration test with real SOPS backend
- [ ] 80%+ coverage

## Dependencies

- HMB-S006 (Python API, which this source delegates to)

## Estimate

2 points
