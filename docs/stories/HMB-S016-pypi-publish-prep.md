---
type: story
project: himitsubako
id: HMB-S016
status: backlog
sprint: 3
created: 2026-04-10
tags: [himitsubako, release, pypi, publishing]
---

# HMB-S016: PyPI Publish Prep

## Summary

Prepare for v0.1.0 release: version bump, CONTRIBUTING.md, SECURITY.md, CHANGELOG.md, and verify the package builds and uploads correctly.

## Motivation

The README promises PyPI availability after v0.1.0. This story ensures the package metadata, documentation, and release process are ready.

## Acceptance Criteria

- [ ] Version bumped from `0.1.0.dev0` to `0.1.0` in `pyproject.toml`
- [ ] `CONTRIBUTING.md` with: development setup, testing instructions, license discipline for new dependencies, PR process
- [ ] `SECURITY.md` with: vulnerability reporting via GitHub Security Advisories
- [ ] `CHANGELOG.md` with v0.1.0 release notes summarizing all shipped features
- [ ] `uv run python -m build` produces valid wheel and sdist
- [ ] `twine check dist/*` passes
- [ ] Test upload to TestPyPI succeeds
- [ ] GitHub Actions release workflow (triggered by tag push) that builds and publishes to PyPI
- [ ] Git tag `v0.1.0` created

## Dependencies

- All other stories complete
- CI pipeline green (HMB-S014)

## Estimate

2 points
