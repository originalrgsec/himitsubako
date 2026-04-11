# Configuration

himitsubako is configured per-project via `.himitsubako.yaml`. Most projects need only a few lines. This page documents the full schema, the precedence rules between env / config / defaults, and the `BackendRouter` dispatcher for per-credential routing.

## File location

`find_config` walks up from the current working directory looking for a file named `.himitsubako.yaml`. The first one found wins. Scripts running from arbitrary directories should either `cd` into the project first or pass an explicit config path to the Python API.

## Top-level schema

```yaml
default_backend: sops        # one of: sops, env, keychain, bitwarden-cli
sops:                         # config for the sops backend (if used)
  secrets_file: .secrets.enc.yaml
  bin: null                   # optional: absolute path to the sops binary
env:                          # config for the env backend (if used)
  prefix: MYAPP_              # strip this prefix from lookups and listings
keychain:                     # config for the keychain backend (if used)
  service: my-project         # keyring service name (defaults to "himitsubako")
bitwarden:                    # config for the bitwarden-cli backend (if used)
  folder: my-project
  bin: null                   # optional: absolute path to the `bw` binary
  unlock_command: null        # optional: shell command that prints the master password
credentials:                  # per-credential routing (optional)
  DEVTO_API_KEY:
    backend: sops
  "CI_*":
    backend: env
```

Every section except `default_backend` is optional. A minimal config is simply:

```yaml
default_backend: sops
sops:
  secrets_file: .secrets.enc.yaml
```

## Precedence rules

For any configurable that has a binary/path/name override, the resolution order is:

1. **Environment variable** (`HIMITSUBAKO_SOPS_BIN`, `HIMITSUBAKO_BW_BIN`, `SOPS_AGE_KEY_FILE`, etc.).
2. **Config file** (`sops.bin`, `bitwarden.bin`, `keychain.service`).
3. **Hard default** (`sops` on `$PATH`, `bw` on `$PATH`, service `"himitsubako"`).

This ordering is the same one `hmb status` reports. When two settings disagree, `hmb status` shows the resolved value.

## Per-credential routing

`BackendRouter` dispatches each key lookup to a concrete backend based on patterns declared under `credentials`. This is how one project can keep its OAuth token in the OS keyring and its deploy key in SOPS without any code branching.

### Declaration order matters

Patterns are evaluated in the order they appear in the YAML file. The router uses `fnmatch` glob matching (`*`, `?`, `[...]`), not regex. The first match wins. A pattern can be an exact key name or a glob.

```yaml
default_backend: sops
sops:
  secrets_file: .secrets.enc.yaml
keychain:
  service: my-project
credentials:
  GITHUB_OAUTH_TOKEN:         # exact match — wins over the glob below
    backend: keychain
  "GITHUB_*":                 # glob — catches everything else
    backend: sops
```

With the config above:

- `get("GITHUB_OAUTH_TOKEN")` hits keychain.
- `get("GITHUB_DEPLOY_KEY")` hits SOPS.
- `get("UNRELATED_KEY")` hits the default backend (SOPS).

Use `hmb status` to see the router table rendered in declaration order:

```
Router:
  GITHUB_OAUTH_TOKEN -> keychain
  GITHUB_* -> sops
```

### Worked example

A Django project that keeps short-lived CI secrets in the environment, long-lived third-party tokens in git-committed SOPS, and personal GitHub OAuth in the OS keyring:

```yaml
default_backend: sops
sops:
  secrets_file: .secrets.enc.yaml
env:
  prefix: CI_
keychain:
  service: django-app
credentials:
  GITHUB_OAUTH_TOKEN:
    backend: keychain
  "CI_*":
    backend: env
```

Now `get("CI_RUN_ID")` hits `os.environ["CI_RUN_ID"]` (no stripping because it matches without the prefix), `get("DJANGO_SECRET_KEY")` hits SOPS, and `get("GITHUB_OAUTH_TOKEN")` hits the OS keyring.

!!! note "env backend prefix + router interaction"
    If you configure `env.prefix` **and** route keys to the env backend via `credentials`, the prefix is applied on lookup: the router sends `CI_TOKEN` to the env backend, and if `env.prefix: CI_` is set, the backend looks up `os.environ["TOKEN"]` (prefix stripped). Usually you want exactly one of the two, not both.

### From Python

The high-level `get()` helper wraps the router:

```python
from himitsubako import get

value = get("GITHUB_OAUTH_TOKEN")
```

For full programmatic control, load the config and instantiate the router directly:

```python
from pathlib import Path
from himitsubako.config import find_config, load_config
from himitsubako.router import BackendRouter

config_path = find_config(Path.cwd())
config = load_config(config_path)
router = BackendRouter(config, project_dir=config_path.parent)

target = router.resolve("GITHUB_OAUTH_TOKEN")
print(target.backend_name)  # e.g. "keychain"
```

`router.resolve(key)` returns the concrete backend instance that will handle the key, which is also what `hmb delete` uses when it needs to name the target backend in the confirmation prompt.

## Environment variables

A few environment variables influence resolution outside the config file. All of them are prefixed `HIMITSUBAKO_` or are inherited from the underlying tool (`SOPS_AGE_KEY_FILE`, `BW_SESSION`).

| Variable | Effect |
|----------|--------|
| `HIMITSUBAKO_SOPS_BIN` | Overrides the sops binary path. Highest precedence. |
| `HIMITSUBAKO_BW_BIN` | Overrides the bw binary path. Highest precedence. |
| `SOPS_AGE_KEY_FILE` | Read by `sops` itself during decrypt. If unset, sops searches the default key locations. |
| `BW_SESSION` | Read by `bw` itself. The bitwarden backend refuses to run in strict mode without it. |

## Validating a config

`hmb status` exits `1` on a malformed config and prints the pydantic error detail to stderr. There is no separate `hmb config validate` command — `hmb status` is the single diagnostic entry point.
