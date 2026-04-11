# Security

This page is the user-facing summary of the project threat model. It describes what himitsubako protects against, what it deliberately does not, and which defenses are load-bearing. The canonical per-threat matrix with status and mitigation IDs lives in `threat-model.md` in the project repo.

## What himitsubako protects against

### At-rest encryption for committed secrets

The SOPS backend stores values encrypted with age. Keys are plaintext (so git diffs remain useful) and values are unreadable without the age private key. A public-repo leak of `.secrets.enc.yaml` exposes the **key names** but not the values.

Load-bearing properties:

- **File mode 0600 on every write.** `SopsBackend._encrypt` writes to a temp file created with `mkstemp`, immediately `fchmod`s it to `0600` before any content is written, atomically `replace()`s into the final path, and then `chmod(0o600)`s again to close the unavoidable POSIX window between rename and chmod. Regression-guarded by `TestSopsBackendFilePermissions::test_new_secrets_file_is_mode_0600` and `test_existing_secrets_file_rewritten_to_0600`.
- **No plaintext ever touches disk outside the temp file.** The value is passed via `tempfile.mkstemp` → `os.fdopen` → `yaml.dump` and the resulting temp file is encrypted in place before the atomic rename.
- **Subprocess timeouts.** Both `sops --decrypt` and `sops --encrypt` are capped at 30 seconds. A hung sops cannot wedge the caller.

### TTY reveal gate

`hmb get KEY` refuses to print a secret value to an interactive terminal unless `--reveal` (`-r`) is passed:

```sh
hmb get DEVTO_API_KEY              # if stdout is a TTY, refuses and exits 1
hmb get DEVTO_API_KEY --reveal     # explicit terminal print
hmb get DEVTO_API_KEY | curl ...   # pipes / redirects are allowed without the flag
```

This is mitigation M-012 against threat T-018: accidental secret exposure in terminal scrollback, screen recordings, and shoulder-surfing. The gate checks for a TTY on stdout, so piping and redirection work unchanged. Regression tests cover both the block-and-error path and the pipe-passthrough path.

### Binary path hijacking

Both the SOPS and Bitwarden CLI backends respect an explicit binary override that takes precedence over `PATH`:

```yaml
sops:
  bin: /opt/homebrew/bin/sops
bitwarden:
  bin: /opt/bitwarden/bw
```

Or via environment variable (`HIMITSUBAKO_SOPS_BIN`, `HIMITSUBAKO_BW_BIN`). Resolution order is env var > config > `PATH`. This is mitigation M-016 against threats T-001 (sops binary path hijack) and T-005 (bw binary path hijack).

### Keychain insecure backend deny-list

On a misconfigured Linux host, the `keyring` library can silently resolve to `PlaintextKeyring` (stores secrets in plaintext under `~/.local/share/python_keyring/`) or `Null` (drops writes on the floor). himitsubako refuses to operate against either:

- The check walks the resolved backend's MRO, not just its leaf class name, so a subclass like `class SafeWrapper(PlaintextKeyring)` cannot bypass the gate.
- On hit, a `BackendError` is raised with a clear remediation message pointing at `gnome-keyring`, macOS Keychain, or an explicit `keyring.set_keyring(...)` call.

Mitigation M-015 against threat T-023. Regression-guarded by `test_keychain_backend.py::TestDenyList`.

### Bitwarden CLI stderr token redaction

Bitwarden's CLI occasionally includes the session token verbatim in error messages. Before interpolating any `bw` stderr into a himitsubako `BackendError`, the backend runs it through a base64-token pattern redactor (`[A-Za-z0-9+/=]{40,}` becomes `[REDACTED]`). This prevents token leaks from propagating into application logs and error reports. Regression-guarded by `test_bitwarden_backend.py::TestStderrRedaction`.

### Bitwarden CLI value-via-stdin

`hmb set` against the bitwarden-cli backend pipes the JSON payload via stdin rather than passing it on the `bw` argv. This keeps plaintext values out of process listings (`ps`, `/proc/<pid>/cmdline`) and is mitigation M-003 against threat T-003.

### direnv `.envrc` shlex quoting

When `hmb direnv-export` writes the managed block, the `secrets_file` path is `shlex.quote`d before interpolation into the eval line. A path containing spaces, dollar signs, or backticks cannot break out of the eval and execute arbitrary code. Regression tests cover all three shapes.

### direnv duplicate-marker refusal

If `.envrc` contains more than one start marker or more than one end marker, `update_envrc` refuses to write and raises a `BackendError` pointing at the user to resolve the duplicates manually. Overwriting would silently merge two blocks and almost always corrupt the file.

## What himitsubako does not protect against

These are deliberate non-goals. If any of them is load-bearing for your threat model, himitsubako alone is not enough.

- **Malicious code running as your user.** Any Python process you run can read every backend you have configured. himitsubako is not a sandboxing layer.
- **Loss of the age private key.** If you lose `~/.config/sops/age/keys.txt` and have not rotated to a new one, the SOPS-backed secrets are unrecoverable. Back up your age key the way you would back up any other root credential.
- **Crash dumps and core files.** Secrets read into memory can end up in process dumps. For extremely sensitive credentials (signing keys, payment keys), consider hardware tokens or HSM-backed storage instead of any in-process library.
- **Leaking via child processes.** When your code shells out to other tools, the full process environment is inherited by default. Decide carefully whether the child needs every variable you have exported.
- **The Bitwarden master password.** If an attacker can read your `unlock_command` output or your `BW_SESSION` env var, they have the same access to your vault that you do. Strict mode (the default) expects you to set `BW_SESSION` yourself so himitsubako never touches the master password.
- **Key enumeration on keychain.** `keyring` does not expose enumeration, so `hmb list` against a keychain-backed project cannot return results. This is a capability limitation, not a leak, but calling it out because users sometimes mistake the friendly message for an error.

## Where to report a vulnerability

Open an issue at the [project tracker](https://github.com/originalrgsec/himitsubako/issues) and mark it as security-sensitive, or email the maintainer. Until v1.0, there is no long-lived security advisory program — expect a conversation, a patched release, and a `SECURITY.md` notice on the repository.
