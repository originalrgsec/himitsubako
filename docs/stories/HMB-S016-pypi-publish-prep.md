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

Prepare the first public PyPI release (targeted at v0.3.0 once Sprint 2 and Sprint 3 land): release documentation, build tooling, and release workflow. Verify the package builds and uploads correctly.

## Motivation

The README promises PyPI availability. v0.1.0 shipped internally (SOPS track rescope) but is not on PyPI. This story ensures the package metadata, documentation, and release process are ready when v0.3.0 is the first public cut.

## Acceptance Criteria

- [ ] Version bumped to the v0.3.0 release target in `pyproject.toml` and `src/himitsubako/__init__.py`
- [ ] `CONTRIBUTING.md` with: development setup, testing instructions, license discipline for new dependencies, PR process
- [ ] `SECURITY.md` with: vulnerability reporting via GitHub Security Advisories
- [ ] `CHANGELOG.md` updated with release notes covering the v0.1.0 → v0.3.0 arc
- [ ] `uv run python -m build` produces valid wheel and sdist
- [ ] `twine check dist/*` passes
- [ ] Test upload to TestPyPI succeeds
- [ ] GitHub Actions release workflow (triggered by tag push) that builds and publishes to PyPI
- [ ] Git tag for the release version created

## Dependencies

- All other stories complete
- CI pipeline green (HMB-S014)

## Estimate

2 points
