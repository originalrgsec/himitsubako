# Getting started

This page takes you from nothing to a working himitsubako project in one sitting. If you want the short version, see the [60-second path on the landing page](index.md).

## Prerequisites

- **Python 3.12 or 3.13.** himitsubako has no Python runtime dependency older than 3.12.
- **`sops` 3.8 or newer** on your `PATH`. The SOPS backend depends on the `--filename-override` flag introduced in 3.8, and older binaries will fail with an unrecognised-flag error. On macOS: `brew install sops`. On Linux, download from the [getsops/sops releases page](https://github.com/getsops/sops/releases); the distro-packaged version is usually too old.
- **`age`** on your `PATH`. On macOS: `brew install age`. On Linux: download from [FiloSottile/age releases](https://github.com/FiloSottile/age/releases).
- **`direnv`** (optional but recommended) if you want the auto-loading workflow.

Verify your tools:

```sh
python --version    # 3.12 or 3.13
sops --version      # 3.8 or newer
age --version
```

## Install

himitsubako is managed with [uv](https://github.com/astral-sh/uv) but installs cleanly via pip too.

=== "uv"

    ```sh
    uv add himitsubako
    ```

=== "pip"

    ```sh
    pip install himitsubako
    ```

Optional extras pull in backends that require extra dependencies:

```sh
pip install 'himitsubako[keychain]'          # macOS Keychain via keyring
pip install 'himitsubako[pydantic-settings]' # HimitsubakoSettingsSource
pip install 'himitsubako[all]'               # both of the above
```

The Bitwarden CLI backend has **no pip dependency** — it shells out to the `bw` system binary and is always available if you install `himitsubako`. See [Bitwarden CLI backend](backends/bitwarden-cli.md) for why.

## Initialize a project

Change into a project directory and run `hmb init`:

```sh
cd my-project/
hmb init
```

`hmb init` creates five things:

1. An **age keypair** at `~/.config/sops/age/keys.txt` if one does not already exist. The public key is printed to stdout. The file is written mode `0600`. If you already have an age key, `hmb init` reuses it.
2. A project-local **`.sops.yaml`** with a `creation_rules` entry listing your age public key as the recipient for `.secrets.enc.yaml`.
3. A project-local **`.envrc`** containing a himitsubako-managed block that decrypts `.secrets.enc.yaml` and exports the keys as environment variables when you `cd` into the directory (assumes direnv).
4. An **empty encrypted `.secrets.enc.yaml`**, encrypted with the age key from step 1.
5. A project-local **`.himitsubako.yaml`** declaring the SOPS backend as default.

You should see output like:

```
Initializing himitsubako...
  age public key: age1examplepubkey0123456789
  wrote .sops.yaml
  wrote .envrc
  wrote .himitsubako.yaml
  wrote .secrets.enc.yaml (encrypted)
  note: consider adding .envrc to .gitignore
Done.
```

## Store your first secret

```sh
hmb set DEVTO_API_KEY
# Value: <paste the value, input is hidden>
# Set 'DEVTO_API_KEY'.
```

Or pass the value inline (useful in scripts, and the value is not echoed):

```sh
hmb set DEVTO_API_KEY --value "sk-live-xxxxxxx"
```

The value is written to `.secrets.enc.yaml`. The plain key name is left in cleartext (so git diffs are useful); only values are encrypted.

## Read it back

```sh
hmb get DEVTO_API_KEY
```

!!! warning "TTY safety gate"
    `hmb get KEY` refuses to print a secret directly to a terminal unless you pass `--reveal`. This prevents accidental leakage into scrollback buffers and terminal logs. Piping or redirecting still works without the flag:

    ```sh
    hmb get DEVTO_API_KEY | xargs -I{} curl -H "Authorization: Bearer {}" ...
    hmb get DEVTO_API_KEY --reveal    # explicit, printed to your terminal
    ```

From Python:

```python
from himitsubako import get

api_key = get("DEVTO_API_KEY")
```

## Use direnv for automatic loading

If you use [direnv](https://direnv.net/), `hmb init` already wrote a `.envrc` containing a managed block that loads all your secrets as environment variables when you `cd` into the directory. Run `direnv allow` once to approve it:

```sh
direnv allow
echo $DEVTO_API_KEY  # value from .secrets.enc.yaml
```

`hmb set` refreshes the managed block automatically. If you ever need to regenerate it manually:

```sh
hmb direnv-export
```

See [direnv integration](integrations/direnv.md) for the marker block format and troubleshooting.

## Rotate the age key

When you want to rotate:

```sh
age-keygen -o ~/.config/sops/age/keys.txt.new
hmb rotate-key --new-key ~/.config/sops/age/keys.txt.new
```

`hmb rotate-key` updates `.sops.yaml` to reference the new public key and re-encrypts every file in `creation_rules`. The old age key can no longer decrypt after rotation. See the [CLI reference](cli-reference.md#hmb-rotate-key) for the full flag list.

## Diagnose misconfigurations

When something looks wrong:

```sh
hmb status
```

`hmb status` is a read-only diagnostic that shows the resolved config file path, the default backend, the SOPS binary path and age recipients from `.sops.yaml`, any `BackendRouter` entries, and a one-line availability check per backend. Never decrypts anything. Pass `--json` for machine-parseable output. See the [CLI reference](cli-reference.md#hmb-status).

## Troubleshooting

### `sops: error loading config: no matching creation rules found`

You are probably running a version of sops older than 3.8. himitsubako passes `--filename-override` to sops so `creation_rules` apply to the real target filename rather than the tempfile the backend uses during encryption; the flag was added in sops 3.8. Upgrade:

```sh
brew upgrade sops
# or download a pinned release from https://github.com/getsops/sops/releases
```

Verify with `sops --version`.

### `refusing to print secret 'FOO' to a terminal without --reveal`

This is the TTY gate. Pass `--reveal` to override it, or redirect/pipe the output. See the safety note above and [Security](security.md#tty-reveal-gate).

### `no .himitsubako.yaml found (run 'hmb init' first)`

Run `hmb init` in the project root, or check whether you are in the correct directory. himitsubako walks up from the current directory looking for `.himitsubako.yaml`; if your project lives under a symlink, make sure the physical directory is where you expect.

### `keychain backend requires 'keyring'; install with 'pip install himitsubako[keychain]'`

The keychain backend is gated behind an optional dependency. Install the extra and retry.

### Anything else

Open an issue at the [project tracker](https://github.com/originalrgsec/himitsubako/issues) with `hmb status` output pasted in (it never prints secret values, so it is safe to share).
