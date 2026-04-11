# SOPS backend

The SOPS backend stores secrets as an age-encrypted YAML file committed to git. It is the primary backend himitsubako ships with and the default for new projects.

## When to use it

- You want secrets to travel with the code (git branches, CI clones, fresh laptops).
- You want to diff and review changes to credential material, not just which keys changed.
- You want a one-command key rotation story.
- You want to survive losing your laptop by regenerating an age key on a fresh machine.

## Requirements

- **`sops` 3.8 or newer** on `PATH`. Older versions lack the `--filename-override` flag the backend depends on (see [Getting started → Troubleshooting](../getting-started.md#troubleshooting) for the error signature).
- **`age`** on `PATH`. Used only for keypair generation during `hmb init` and `hmb rotate-key`; `sops` itself handles the actual encrypt / decrypt with the recipient already specified in `.sops.yaml`.
- An age private keyfile readable by the current user. Default location: `~/.config/sops/age/keys.txt`. The path can be overridden via the standard `SOPS_AGE_KEY_FILE` environment variable.

## Configuration

```yaml
default_backend: sops
sops:
  secrets_file: .secrets.enc.yaml   # path is relative to the project root
  bin: null                          # optional absolute path override
```

`bin` is resolved as `HIMITSUBAKO_SOPS_BIN` > `sops.bin` > `sops` on `PATH`. Use the env variable or the config override when you have multiple sops versions installed and need to pin one.

### The `.sops.yaml` file

`hmb init` also writes a project-local `.sops.yaml` — this is a file sops itself reads for `creation_rules`, not a himitsubako config. It looks like this:

```yaml
creation_rules:
  - path_regex: \.secrets\.enc\.yaml$
    age: age1examplepubkey0123456789
```

Multiple recipients are supported by separating them with commas in the `age:` field, or by adding additional `creation_rules` entries with different `path_regex` values. `hmb rotate-key` rewrites every `age:` field in every rule to the new public key.

## Storage format

himitsubako stores top-level string→string pairs:

```yaml
DEVTO_API_KEY: ENC[AES256_GCM,data:...,iv:...,tag:...,type:str]
GITHUB_TOKEN: ENC[AES256_GCM,data:...,iv:...,tag:...,type:str]
```

**Keys are plaintext; only values are encrypted.** This is a deliberate trade-off: it gives you useful git diffs ("we added `DEVTO_API_KEY` in this commit") at the cost of leaking key names. If you cannot tolerate leaking key names, use a different backend for those specific credentials via per-credential routing.

## File safety

The SOPS backend enforces several on-disk properties:

- **Mode `0600` on every write.** `.secrets.enc.yaml` is created with a umask-proof temp file (`os.fchmod` before the write), the content is written to it, and the atomic `replace()` installs it at the final path. Immediately after, a `chmod(0o600)` on the final path closes any OS-level umask races. Tests assert `stat.S_IMODE(...) == 0o600` after both the initial write and subsequent updates (the T-010 regression guard).
- **Atomic writes.** The backend never truncates `.secrets.enc.yaml` in place. A corrupted encrypt leaves the original file untouched.
- **Subprocess timeouts.** Both `sops --decrypt` and `sops --encrypt` are run with a 30-second timeout. A hung sops is surfaced as a `BackendError` rather than hanging the caller.
- **`--filename-override`.** The backend passes `--filename-override <real_target>` so sops applies `.sops.yaml`'s `path_regex` against the real secrets filename and not the mkstemp tempfile. Without this flag, every encrypt would fail with `error loading config: no matching creation rules found`. The unit test `TestSopsBackendFilenameOverride` pins the argv shape so the flag cannot silently regress.

## Rotation

See [`hmb rotate-key`](../cli-reference.md#hmb-rotate-key). In short:

```sh
age-keygen -o ~/.config/sops/age/keys.txt.new
hmb rotate-key --dry-run --new-key ~/.config/sops/age/keys.txt.new
hmb rotate-key          --new-key ~/.config/sops/age/keys.txt.new
```

After rotation the old key can no longer decrypt the secrets file. Keep the old keyfile around until you have verified the new setup.

## Minimal working example

```sh
cd my-project/
hmb init
hmb set DEVTO_API_KEY --value "sk-live-xxxxxxx"
hmb get DEVTO_API_KEY | cat                 # pipe read, no --reveal needed
hmb list
hmb delete DEVTO_API_KEY --force
hmb status
```

## Threat model summary

Relevant threats from the project threat model, with mitigations as implemented:

- **T-010 — insecure file mode.** Mitigated by `os.fchmod` on the pre-rename temp file plus post-rename `chmod`. Regression-guarded by unit tests.
- **T-001 — sops binary path hijack.** Mitigated by the `HIMITSUBAKO_SOPS_BIN` env var and `sops.bin` config field, which take precedence over `PATH`.
- **T-004 — sops hang denial-of-service.** Mitigated by the 30-second subprocess timeout.
- **T-018 / OQ-4 — TTY reveal leakage.** Not specific to SOPS but applies to every backend: `hmb get` refuses to print to a terminal without `--reveal`.

See [Security](../security.md) for the user-facing summary and `threat-model.md` in the project repo for the full per-threat matrix.
