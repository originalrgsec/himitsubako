# Environment variable backend

The env backend reads credentials from `os.environ`. It is a first-class backend, not a fallback: you can declare `default_backend: env` in `.himitsubako.yaml`, or route specific keys to it via `credentials`, or rely on it as the automatic fallback when no `.himitsubako.yaml` is found.

## When to use it

- **CI pipelines** that inject credentials via `env:` blocks in a workflow file.
- **Containers** where the orchestration layer (Kubernetes, systemd, docker-compose) is the source of truth for secrets.
- **12-factor apps** that already treat environment variables as the credential contract.
- **Fallback in libraries** — the high-level `himitsubako.get()` helper resolves through env when no config file is found, so third-party libraries can call it without requiring consumers to create a himitsubako config.

## Configuration

```yaml
default_backend: env
env:
  prefix: MYAPP_    # optional — if set, lookups and listings strip this prefix
```

With `prefix: MYAPP_`, `get("DB_PASSWORD")` resolves to `os.environ["MYAPP_DB_PASSWORD"]` and `hmb list` returns every `MYAPP_*` var with the prefix stripped.

Without a prefix, `get(key)` looks up `os.environ[key]` verbatim and `hmb list` returns **the entire process environment**, which is rarely useful. `hmb list` prints a stderr warning in this case:

```
Warning: env backend has no prefix configured; listing all process environment variables.
Set 'env.prefix' in .himitsubako.yaml to scope this to your application's keys.
```

## Read-only semantics

The env backend is **read-only by design**. `set()` and `delete()` both raise `BackendError("env", "env backend is read-only")`. This is enforced because:

1. Writing to `os.environ` in-process does not persist beyond the current process.
2. Writing to the launching shell's environment is not portable across shells or OSes.
3. Silently accepting writes would mislead users into thinking changes are persisted.

If you run `hmb set FOO --value bar` against an env-backed config, you get exit code `2` and a clear message. The `hmb delete` command treats env read-only rejection the same way.

## Fallback chain

When no `.himitsubako.yaml` exists anywhere in the directory ancestry, the high-level `himitsubako.get()` falls back to `EnvBackend()` with no prefix. This is the "works out of the box" path for libraries that want to use himitsubako without requiring consumer configuration:

```python
# In library code — no config file assumed.
from himitsubako import get

api_key = get("PROVIDER_API_KEY")   # resolves os.environ["PROVIDER_API_KEY"]
```

`hmb status` run from a directory with no config file reports:

```
Config: <not found>
  searched: .himitsubako.yaml upward from cwd
Default backend: env
Backends:
  env: ok
```

## Minimal working example

```sh
export MYAPP_DB_PASSWORD="hunter2"
cat > .himitsubako.yaml <<'EOF'
default_backend: env
env:
  prefix: MYAPP_
EOF

hmb get DB_PASSWORD    # pipe read, no --reveal needed
# hunter2
hmb list
# DB_PASSWORD
```

## Threat model summary

The env backend inherits the process environment's security properties. Relevant notes:

- **Leak via child processes.** Any subprocess inherits the parent environment unless explicitly sanitised. When your code shells out to third-party tools, decide carefully whether to pass the full env or a filtered subset.
- **Leak via crash dumps / core files.** Environment variables are included in process memory dumps. Projects handling very-sensitive credentials (payment keys, signing keys) should use SOPS or keychain instead.
- **No at-rest encryption.** Secrets live in plaintext for the lifetime of the process.
- **`hmb list` without a prefix warning.** `hmb list` emits a stderr warning when the env backend has no prefix configured, because listing the entire process environment is almost never what the user wants.

See [Security](../security.md) for the user-facing summary.
