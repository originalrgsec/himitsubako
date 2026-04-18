# CLI reference

Every `hmb` command with synopsis, options, and exit codes. Assumes you are in a project with a `.himitsubako.yaml`; `hmb status` is the exception and can be run from anywhere.

## Exit codes

All commands follow the same convention:

| Exit code | Meaning |
|-----------|---------|
| 0 | Success (or a soft miss like `hmb delete --missing-ok` hitting a nonexistent key) |
| 1 | Expected failure: secret not found, config not found, usage error |
| 2 | Backend error: read-only backend rejected a write, sops binary missing, keyring refused the request, etc. |

Where a command deviates from this table, the deviation is called out in its section below.

---

## `hmb init`

Scaffold a project for himitsubako: generate an age keypair (if needed), write `.sops.yaml`, `.envrc`, `.himitsubako.yaml`, and an empty encrypted `.secrets.enc.yaml`.

**Synopsis**

```sh
hmb init [--force]
```

**Options**

- `--force` — overwrite existing files. Without this flag, any file that already exists is left alone and `hmb init` logs `skip <file> (exists, use --force to overwrite)`.

**Behavior**

1. Reads `~/.config/sops/age/keys.txt` if it exists; otherwise calls `age-keygen` and writes a new keypair there, mode `0600`.
2. Writes `.sops.yaml` with a `creation_rules` entry naming the age public key as the recipient for `\.secrets\.enc\.yaml$`.
3. Writes `.envrc` with a himitsubako-managed block that calls `sops --decrypt` on the encrypted secrets file and exports the keys as environment variables.
4. Writes `.himitsubako.yaml` declaring `sops` as the default backend.
5. Writes an empty `.secrets.enc.yaml` and encrypts it in place with `sops`.

**Examples**

```sh
cd my-project/
hmb init
# first run — scaffolds everything

hmb init --force
# regenerate .envrc and .himitsubako.yaml after hand-editing
```

---

## `hmb get`

Look up a secret by key.

**Synopsis**

```sh
hmb get KEY [--reveal | -r]
```

**Options**

- `--reveal`, `-r` — print the secret to the terminal even when stdout is a TTY. Required for human-readable reads; not required when piping or redirecting.

**Exit codes**

- `0` — secret found and printed.
- `1` — secret not found, or TTY gate blocked the print (`--reveal` was required but not passed).

**Examples**

```sh
hmb get DEVTO_API_KEY | xargs -I{} curl -H "Authorization: Bearer {}" https://dev.to/api/me
hmb get DEVTO_API_KEY --reveal        # explicit terminal print
```

!!! warning "TTY gate"
    Without `--reveal`, `hmb get` refuses to print a secret to an interactive terminal. This protects against terminal scrollback leaks and shoulder-surfing. See [Security → TTY reveal gate](security.md#tty-reveal-gate).

---

## `hmb set`

Store or update a secret.

**Synopsis**

```sh
hmb set KEY [--value VALUE]
```

**Options**

- `--value VALUE` — set the value inline. If omitted, `hmb set` prompts interactively with hidden input.

**Exit codes**

- `0` — secret stored.
- `2` — backend rejected the write. The env backend is read-only and always rejects; SOPS rejects if the sops binary is missing or the age recipient cannot encrypt.

**Examples**

```sh
hmb set DEVTO_API_KEY
# Value: (hidden prompt)

hmb set DEVTO_API_KEY --value "sk-live-xxxxxxx"
```

After a successful set against the SOPS backend, `hmb set` best-effort-refreshes the `.envrc` managed block so direnv reloads include the new key. Failure to refresh is surfaced as a stderr warning but does not change the exit code.

---

## `hmb list`

List every key the active backend knows about, sorted alphabetically.

**Synopsis**

```sh
hmb list
```

**Behavior by backend**

- **SOPS** — decrypts `.secrets.enc.yaml` and lists its top-level keys.
- **env** — returns every environment variable matching the configured prefix, with the prefix stripped. If no prefix is configured, emits a stderr warning ("env backend has no prefix configured; listing all process environment variables") and returns the full environment.
- **keychain** — the `keyring` library does not expose enumeration. `hmb list` prints a friendly message and exits 0 without listing anything: `Backend 'keychain' does not support listing: ...`. Consult your project's `.himitsubako.yaml` for the expected key names.
- **bitwarden-cli** — returns every item name in the configured Bitwarden folder.
- **BackendRouter** (per-credential routing) — aggregates `list_keys()` from every referenced backend, skipping those that raise.

**Exit codes**

- `0` — always, even when a backend cannot enumerate. The message is informational.

---

## `hmb delete`

Remove a secret from the backend that owns it. (HMB-S018.)

**Synopsis**

```sh
hmb delete KEY [--force | --yes] [--missing-ok]
```

**Options**

- `--force` / `--yes` — skip the interactive confirmation prompt. The two names are aliases.
- `--missing-ok` — exit 0 silently if the key does not exist, instead of treating absence as an error.

**Behavior**

1. Resolves the backend that owns `KEY` (may be the default backend or a `BackendRouter` target).
2. Unless `--force` / `--yes` is passed, prompts `Delete secret 'KEY' from <backend_name>? [y/N]`. The prompt names the *resolved* backend (e.g. `sops`), not the router wrapper.
3. Calls the backend's `delete()`.

**Exit codes**

- `0` — secret deleted, or prompt declined, or `--missing-ok` hit.
- `1` — secret not found (absent `--missing-ok`).
- `2` — backend error (env backend read-only, sops binary missing, keyring rejected the request, etc.).

**Examples**

```sh
hmb delete API_TOKEN
# Delete secret 'API_TOKEN' from sops? [y/N]: y
# deleted API_TOKEN

hmb delete API_TOKEN --force
hmb delete OLD_KEY --missing-ok      # idempotent cleanup
```

---

## `hmb status`

Read-only diagnostic. Prints the resolved config path, the default backend, the SOPS binary and age recipients, the `BackendRouter` table in declaration order, and a one-line availability check per referenced backend. **Never** reads, writes, or enumerates any credential. (HMB-S019.)

**Synopsis**

```sh
hmb status [--json]
```

**Options**

- `--json` — emit a single JSON object for scripting. Same fields as the human-readable output: `config_path`, `default_backend`, `sops` (`binary` + `recipients`), `router` (ordered list of `{pattern, backend}` entries), and `backends` (per-backend `{status, detail}`).

**Availability checks**

- **SOPS** — `sops --version` must exit 0 within 5 seconds. The resolved binary path (from `HIMITSUBAKO_SOPS_BIN` > `sops.bin` config > `sops` on PATH) is printed.
- **env** — always `ok`; no ping required.
- **keychain** — imports `keyring`, calls `get_keyring()`, and walks the resolved class MRO against the insecure-backend deny-list. Unavailable if the import fails, the deny-list hits, or the plugin raises.
- **bitwarden-cli** — `bw status` must exit 0. On success, the lock state (`unlocked`, `locked`, `unauthenticated`) is surfaced as detail.

**Exit codes**

- `0` — config loaded cleanly, even if some backends are unavailable. Unavailability is information, not an error.
- `1` — the config file is malformed or cannot be parsed.

**Examples**

```sh
hmb status
# Config: /path/to/project/.himitsubako.yaml
# Default backend: sops
# SOPS:
#   binary: /opt/homebrew/bin/sops
#   recipients: age1pubkey...
# Backends:
#   sops: ok (sops 3.12.2 (latest))

hmb status --json | jq '.backends'
```

---

## `hmb rotate-key`

Re-encrypt every SOPS-backed file in `creation_rules` with a new age keypair.

**Synopsis**

```sh
hmb rotate-key --new-key PATH [--dry-run] [--rule REGEX]
```

**Options**

- `--new-key PATH` — path to a new age keys file. Must already exist; `hmb rotate-key` does not call `age-keygen` for you.
- `--dry-run` — print what would change without touching any file.
- `--rule REGEX` — when `.sops.yaml` has more than one `creation_rule` with an `age` recipient, select which one to rotate. The value is a regular expression matched against each rule's `path_regex`; it must resolve to exactly one rule.

**Behavior**

1. Reads the new public key from the `# public key:` comment line of `--new-key`.
2. Determines which `creation_rules` entry in `.sops.yaml` to update:
   - If exactly one rule has an `age` recipient, it is updated (no flag needed).
   - If more than one rule has an `age` recipient and `--rule` was **not** supplied, the command aborts with an error listing each rule's `path_regex` and current `age` recipient. This avoids silently collapsing a multi-recipient configuration to a single key.
   - If `--rule` **was** supplied, the regex is matched against each rule's `path_regex`. Zero matches or more than one match both abort with a non-zero exit and list the rules for reference.
3. Runs `sops updatekeys --yes` against the secrets file, which re-encrypts with the new recipient and removes the old one.

After rotation, the old age key can no longer decrypt the secrets file. Keep the old keys file around until you have verified the new one works.

**Exit codes**

- `0` — rotation complete (or dry-run printed).
- non-zero — usage error, no `.sops.yaml`, no public key comment in the new keys file, ambiguous multi-rule `.sops.yaml` without `--rule`, or `--rule` regex with zero/many matches.
- non-zero from click for backend errors — `sops updatekeys` failure is surfaced with stderr detail.

**Examples**

```sh
age-keygen -o ~/.config/sops/age/keys.txt.new
hmb rotate-key --dry-run --new-key ~/.config/sops/age/keys.txt.new
hmb rotate-key --new-key ~/.config/sops/age/keys.txt.new

# Multi-rule .sops.yaml — select which rule to rotate
hmb rotate-key --new-key ~/.config/sops/age/keys.txt.new --rule 'prod/.*'
```

---

## `hmb direnv-export`

Regenerate the himitsubako-managed block in the project `.envrc`. Useful after hand-editing or if the marker block got out of sync with the secrets file.

**Synopsis**

```sh
hmb direnv-export
```

No options. Writes the managed block between the start/end markers and leaves any surrounding `.envrc` content untouched. See [direnv integration](integrations/direnv.md) for the marker format and the duplicate-marker safety guard.

**Exit codes**

- `0` — `.envrc` updated (or created if absent).
- non-zero on usage error (no `.himitsubako.yaml` in the current directory).
