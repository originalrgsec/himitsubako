---
type: story
project: himitsubako
id: HMB-S014
status: backlog
sprint: 3
created: 2026-04-10
tags: [himitsubako, ci, github-actions]
---

# HMB-S014: CI Pipeline

## Summary

Set up GitHub Actions CI with linting, type checking, and test matrix across Python 3.12 and 3.13.

## Motivation

Automated quality gates before merge. Required for a credible open-source release.

## Acceptance Criteria

- [ ] `.github/workflows/ci.yml` with:
  - Matrix: Python 3.12, 3.13
  - Steps: checkout, install uv, `uv sync --all-extras`, ruff check, mypy, pytest with coverage
  - Install `sops` and `age` binaries for integration tests
  - Coverage report uploaded as artifact
  - Fail if coverage < 80%
- [ ] Runs on push to `main` and on pull requests
- [ ] Badge in README linking to workflow status
- [ ] Workflow passes on current codebase

## Dependencies

- HMB-S013 (integration tests, so the pipeline has something meaningful to run)

## Estimate

2 points
