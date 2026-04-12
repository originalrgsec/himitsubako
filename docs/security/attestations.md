# Release attestations (PEP 740 / Sigstore)

Starting with **v0.4.0**, every himitsubako release on PyPI ships with a
[PEP 740](https://peps.python.org/pep-0740/) provenance attestation signed by
[Sigstore](https://www.sigstore.dev/). The attestation cryptographically binds
the release artifacts (wheel + sdist) to the exact GitHub Actions workflow run
that produced them, so downstream users can verify that a given file really
came from the `originalrgsec/himitsubako` release pipeline and was not
tampered with in transit.

This page explains what the attestations cover, how to verify them, and what
the expected signing identity is. If you do not need supply-chain verification,
you can safely ignore this page — `pip install himitsubako` still works
exactly as before.

## What the attestation covers

Each release artifact on PyPI has an associated attestation bundle (a
`.publish.attestation` file) containing:

- A **Sigstore signature** over the artifact's SHA-256 digest.
- A **signing certificate** minted by Fulcio, bound to the short-lived OIDC
  identity of the GitHub Actions workflow run that produced the artifact.
- A **transparency log entry** in [Rekor](https://docs.sigstore.dev/logging/overview/),
  making the attestation publicly auditable and append-only.

The attestation does **not** cover:

- The source code at the tagged commit (you can verify that separately via
  `git tag -v <tag>` if the tag is signed, or by checking the GitHub release
  page against the tag).
- The reproducibility of the build (himitsubako does not ship reproducible
  builds as of v0.4.0).

## The expected signing identity

The release workflow lives at `.github/workflows/release.yml` on the
`originalrgsec/himitsubako` repository and publishes through the `pypi-release`
GitHub Actions environment. Any valid himitsubako attestation therefore has a
signing identity of:

```
https://github.com/originalrgsec/himitsubako/.github/workflows/release.yml@refs/tags/v<VERSION>
```

with an OIDC issuer of:

```
https://token.actions.githubusercontent.com
```

If you ever verify an attestation and the certificate identity does **not**
match the pattern above (wrong repo, wrong workflow file, wrong tag), treat
the release as compromised and do not install it.

## How to verify a release

There are two supported verification paths: the GitHub CLI and the
`sigstore` Python package. Either is sufficient.

### Option 1: `gh attestation verify` (GitHub CLI)

This is the quickest option if you already have `gh` installed and
authenticated. `gh` knows how to pull the attestation bundle from PyPI and
check it against the GitHub repository identity in one shot.

```sh
# Download the wheel from PyPI (or use one you already have cached)
pip download himitsubako==0.4.0 --no-deps --dest /tmp/himitsubako-verify

# Verify the attestation against the repo identity
gh attestation verify /tmp/himitsubako-verify/himitsubako-0.4.0-py3-none-any.whl \
  --repo originalrgsec/himitsubako
```

Success looks like:

```
Loaded digest sha256:... for file:///tmp/himitsubako-verify/...
✓ Verification succeeded!
  - Attestation #1
    - Build repo: originalrgsec/himitsubako
    - Build workflow: .github/workflows/release.yml@refs/tags/v0.4.0
    - Signer workflow: .github/workflows/release.yml@refs/tags/v0.4.0
```

### Option 2: `python -m sigstore verify identity`

If you would rather not install `gh`, the `sigstore` Python package can verify
the same attestation directly. This is the path we recommend for CI jobs that
want to pin their toolchain to pip-installable tools.

```sh
pip install sigstore
pip download himitsubako==0.4.0 --no-deps --dest /tmp/himitsubako-verify

python -m sigstore verify identity \
  --cert-identity 'https://github.com/originalrgsec/himitsubako/.github/workflows/release.yml@refs/tags/v0.4.0' \
  --cert-oidc-issuer 'https://token.actions.githubusercontent.com' \
  /tmp/himitsubako-verify/himitsubako-0.4.0-py3-none-any.whl
```

Replace `v0.4.0` with the version you are actually installing. A successful
verify prints `OK` on the artifact line and exits 0.

## What verification does not replace

Attestations prove **provenance**, not **safety**. A maliciously-authored
commit merged to `main` and then tagged through the release workflow will
produce a valid attestation, because the attestation binds to the workflow,
not to the code. Attestation verification should be one layer of a wider
supply-chain posture that also includes:

- Pinning your installs with `pip install --require-hashes` from a lockfile,
  so tampered wheels cannot silently be swapped under you at install time.
- Code review of dependency updates before they land in `pyproject.toml` or
  your lockfile.
- Monitoring the
  [transparency log](https://search.sigstore.dev/?logIndex=) for unexpected
  release entries against the `originalrgsec/himitsubako` identity.

The full residual risk analysis lives in the project threat model under
T-034 (attestation binding misconfiguration) and T-038 (downstream
non-verification). Both are tracked as known limitations of the v0.4.0
shipping posture.

## When verification fails

If either tool reports a verification failure — whether a signature mismatch,
an identity mismatch, or an unknown Rekor entry — do **not** install the
release. File an issue at
[github.com/originalrgsec/himitsubako/issues](https://github.com/originalrgsec/himitsubako/issues)
with the verification command and output. If you have a pinned production
environment, roll back to the last version you were able to verify.
