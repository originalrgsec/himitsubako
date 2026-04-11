# himitsubako

> 秘密箱 — "secret box." Named after Japanese puzzle boxes from the Hakone region, which open through a sequence of sliding moves rather than a single key.

**A multi-backend credential abstraction for solo Python developers.** SOPS + age as the primary backend, with optional macOS Keychain, Bitwarden CLI, direnv, and environment variable support. MIT licensed.

## What it is

himitsubako gives you one consistent way to read, write, rotate, and audit credentials — API keys, OAuth tokens, session cookies, PATs, database passwords — across every project on your laptop and every machine you work from. Secrets live in whichever store makes sense for them: encrypted YAML in git for the things you want portable, your OS keyring for long-lived personal tokens, Bitwarden if you already pay for it. Your code and your CLI treat them uniformly.

```python
from himitsubako import get

api_key = get("DEVTO_API_KEY")
```

```sh
hmb set DEVTO_API_KEY
hmb get DEVTO_API_KEY
hmb list
hmb status
```

## Design principles

1. **Encrypt at rest, in git.** SOPS + age is the primary backend. You can commit `.secrets.enc.yaml` to a public repo without leaking the values.
2. **Per-credential routing.** One project can keep its OAuth token in macOS Keychain and its deploy key in SOPS. The CLI and Python API route transparently via [`BackendRouter`](configuration.md#per-credential-routing).
3. **External CLI tools, not vendor SDKs.** The Bitwarden backend shells out to the `bw` binary rather than pulling in the non-OSI `bitwarden-sdk`. No vendor lock-in, no license surprises.
4. **Explicit safety rails.** `hmb get` refuses to print a secret to a TTY without `--reveal`. `.secrets.enc.yaml` is written mode `0600` under a umask-proof path. Bitwarden CLI stderr is redacted before surfacing in error messages.
5. **Small, auditable surface.** The library is around 1000 lines of Python. Reviewing it is a weekend project, not a career.

## Where to go next

- [Getting started](getting-started.md) — the 60-second onboarding path expanded to a full walkthrough with troubleshooting.
- [CLI reference](cli-reference.md) — every command with synopsis, options, and exit codes.
- [Configuration](configuration.md) — `.himitsubako.yaml` schema and the `BackendRouter` dispatcher.
- **Backends** — one page per backend:
    - [SOPS](backends/sops.md)
    - [Environment](backends/env.md)
    - [Keychain](backends/keychain.md)
    - [Bitwarden CLI](backends/bitwarden-cli.md)
- **Integrations** — [pydantic-settings](integrations/pydantic-settings.md) and [direnv](integrations/direnv.md).
- [Security](security.md) — the threat model in user-facing language.

## Project status

Alpha. Sprint 3 (v0.3.0) adds CI, PyPI publish, and this docs site. Expect occasional breaking changes until the 1.0 tag lands. See the [changelog](changelog.md) for details.
