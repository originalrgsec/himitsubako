# himitsubako

> 秘密箱 — "secret box." Named after Japanese puzzle boxes from the Hakone region, which open through a sequence of sliding moves rather than a single key.

**A multi-backend credential abstraction for solo Python developers.** SOPS + age as the primary backend, with optional macOS Keychain, Bitwarden CLI, direnv, and environment variable support. MIT licensed.

## Who this is for

You are a solo developer. You have credentials — API keys, OAuth tokens, session cookies, PATs, database passwords — scattered across `.env` files, your shell history, a dotfile repo, and probably a sticky note somewhere. You want one consistent way to manage them that:

- Works offline, on your laptop, without a server
- Commits encrypted secrets to git so they're backed up and portable
- Lets you rotate the master key across every project in one command
- Doesn't require you to trust a SaaS vendor
- Doesn't require you to run a daemon
- Plays nicely with `pydantic-settings`, `direnv`, `docker-compose`, `launchd`, and `systemd`
- Gets out of your way when you just want to read an environment variable

**himitsubako is not for teams.** If you need RBAC, audit logs, dynamic database credentials, or service-to-service authentication between multiple humans and services, you want HashiCorp's [OpenBao](https://github.com/openbao/openbao) or a commercial secrets manager. himitsubako deliberately stays small so it can stay correct.

## The opinionated answer

Most solo-dev secrets pain comes from trying to homebrew a single pattern that covers everything. himitsubako picks one primary pattern and supports a handful of escape hatches.

**Primary pattern: SOPS + age + direnv**

- [SOPS](https://github.com/getsops/sops) (CNCF) encrypts YAML/JSON files in place. Only values are encrypted — keys stay plaintext so git diffs stay readable.
- [age](https://github.com/FiloSottile/age) is the modern, simple encryption tool SOPS uses as a backend. One keypair per developer, stored in `~/.config/sops/age/keys.txt`.
- [direnv](https://direnv.net/) is a shell hook that loads environment variables when you `cd` into a project directory and unloads them when you leave.

Combined, you get: encrypted secrets committed to git, decrypted into your shell env automatically when you enter the project, loaded into Python via `os.environ[...]` like any other env var. No library import required for 90% of use cases.

**When you need the library**, himitsubako provides:

1. A Python API for runtime credential lookup, rotation, and backend switching
2. A CLI for interactive secret management (`hmb get`, `hmb set`, `hmb list`, `hmb delete`, `hmb status`, `hmb rotate`)
3. A [`pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) source for declarative credential loading in Python applications
4. Opinionated scaffolding (`hmb init`) that creates your age key, writes the `.sops.yaml`, generates an example `.envrc`, and encrypts an empty secrets file — all in one command
5. Additional backends for cases where SOPS doesn't fit: macOS Keychain (via `keyring`), Bitwarden CLI (via `bw` subprocess), environment variables

## Backends

| Backend | Use when | Requires |
|---|---|---|
| **sops** (primary) | You want encrypted secrets in git, portable across machines, rotatable with one command | `sops` >= 3.8 + `age` binaries on PATH |
| **keychain** | You want OS-native storage that survives repo deletion, typically for personal long-lived tokens | macOS (Linux/Windows via `keyring` fallback) |
| **bitwarden-cli** | You already use Bitwarden and want your dev credentials in the same vault as your passwords | Bitwarden account, `bw` CLI on PATH |
| **env** | 12-factor simplicity, CI/CD pipelines, containers with env injection | Nothing |
| **direnv helper** | Automatic env var loading when entering a project directory | `direnv` binary on PATH |

Backends are selected per-credential via a project-level config file. Your `devto_api_key` can live in SOPS while your `aws_access_key_id` lives in macOS Keychain, all accessed through the same `himitsubako.get(...)` call.

## 60-second getting started

Install (will be available on PyPI after v0.1.0 ships):

```sh
pip install himitsubako
```

Initialize a project:

```sh
cd my-project/
hmb init
```

That creates: an age keypair (if you don't have one), `.sops.yaml` with your public key as the recipient, an empty encrypted `.secrets.enc.yaml`, a `.envrc` that auto-loads the secrets via direnv, and a `.himitsubako.yaml` config file.

Add a secret:

```sh
hmb set DEVTO_API_KEY
# prompts for value with masked input, encrypts, writes to .secrets.enc.yaml
```

Delete a secret:

```sh
hmb delete DEVTO_API_KEY
# prompts for confirmation; pass --force (alias --yes) to skip,
# or --missing-ok to exit 0 silently if the key is absent
```

Read it in Python:

```python
import os
key = os.environ["DEVTO_API_KEY"]  # loaded by direnv on cd
```

Or programmatically, if direnv isn't your style:

```python
from himitsubako import get
key = get("DEVTO_API_KEY")
```

Diagnose configuration and backend availability:

```sh
hmb status
# prints config path, default backend, SOPS binary and age recipients,
# any router patterns, and a one-line availability check per backend
# (e.g. "sops: ok (sops 3.8.1)", "keychain: unavailable (...)").
# Pass --json to emit the same information as a single JSON object.
```

Rotate the master age key:

```sh
hmb rotate-key --new-key ~/.config/sops/age/keys.txt.new
# re-encrypts every .secrets.enc.yaml in configured projects with the new key
```

## Integration with pydantic-settings

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from himitsubako.pydantic import HimitsubakoSettingsSource

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    devto_api_key: str
    hashnode_pat: str
    database_url: str

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings,
                                   env_settings, dotenv_settings, file_secret_settings):
        return (init_settings, HimitsubakoSettingsSource(settings_cls), env_settings)
```

Now `AppSettings()` pulls from himitsubako first, then falls back to environment variables.

## Why not ...?

**Why not just use SOPS directly?**
You can, and for many projects that's the right answer. himitsubako adds value when: (a) you want a consistent Python API across SOPS and other backends, (b) you need programmatic credential rotation mid-process, (c) you want `pydantic-settings` integration, or (d) you want the opinionated `hmb init` command that wires everything up correctly the first time. If none of those apply, use SOPS directly — that's exactly the primary pattern this library endorses.

**Why not [teller](https://github.com/tellerops/teller)?**
teller is excellent and covers a broader backend matrix than himitsubako. It's written in Go. If you're a Go developer or want a language-agnostic CLI, teller is probably a better fit. himitsubako is Python-native — you can import it, not just shell out to it — which matters if you want programmatic access in Python code or integration with `pydantic-settings`.

**Why not HashiCorp Vault or OpenBao?**
Vault is BUSL-licensed (not OSI-approved, restrictive terms for commercial use). OpenBao is the Linux Foundation's MPL-2.0 fork of Vault and is a great fit for team environments with runtime daemon, RBAC, audit log, and dynamic secret requirements. If your project has any of those needs, use OpenBao directly via [`hvac`](https://github.com/hvac/hvac). himitsubako is deliberately scoped below that threshold — it's for the solo case where the overhead of running a daemon isn't justified.

**Why not a commercial SaaS (Doppler, Infisical, 1Password Secrets Automation)?**
Those are legitimate options if you prefer a GUI for credential management, want vendor-managed rotation, or need network-accessible secrets for serverless workloads. himitsubako optimizes for offline-first, zero-cost, zero-trust-in-third-parties. Pick based on your constraints.

**Why not Bitwarden Secrets Manager?**
The Bitwarden Secrets Manager SDK is distributed under a proprietary license (Bitwarden SDK License Agreement v1) that is not OSI-approved and contains clauses that are incompatible with MIT-licensed distribution. The Bitwarden **Password Manager** CLI (`bw`) is GPL-3.0 and is safe to invoke via subprocess — and that's the integration himitsubako ships. If you want to store your dev credentials in your Bitwarden personal vault, the `bitwarden-cli` backend has you covered.

**Why named "himitsubako"?**
秘密箱 (himitsu-bako) literally means "secret box" in Japanese. Himitsu-bako are traditional puzzle boxes from the Hakone region of Japan, dating to the 1830s, that open through a sequence of sliding moves rather than a single external key. Secrets accessed through a sequence of moves (age keys, SOPS paths, CLI subcommands, direnv hooks) fit the metaphor better than "another library with 'key' or 'vault' in the name." Also, `keymaster` was taken on PyPI.

## Prior art

The backend protocol and several of the backend implementations (age, env, keyring, bitwarden-cli, 1password) are inspired by and extracted from the secrets module in [open-workspace-builder](https://github.com/originalrgsec/open-workspace-builder), a personal workspace tool under the same author. himitsubako exists because OWB's secrets module proved the abstraction was useful enough to extract into a standalone library that other projects (personal and otherwise) could adopt without depending on OWB.

## Project status

**v0.1.0 is in development.** The backends listed above are the v0.1.0 scope. The library will be published to PyPI when v0.1.0 is ready. Until then, it can be installed directly from the git repository for testing.

See [stories/](https://github.com/originalrgsec/himitsubako/tree/main/docs/stories) for the v0.1.0 roadmap (coming soon).

## License

MIT. See [LICENSE](./LICENSE).

## Contributing

Issues and pull requests welcome. Please read the (forthcoming) CONTRIBUTING.md before opening a PR. The project follows a strict license discipline for any new dependency — see the pre-install gate pattern documented in CONTRIBUTING.

## Security

If you believe you've found a security vulnerability in himitsubako, please report it privately via GitHub Security Advisories rather than opening a public issue. Details in SECURITY.md (forthcoming).
