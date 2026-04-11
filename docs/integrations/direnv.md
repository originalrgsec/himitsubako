# direnv integration

[direnv](https://direnv.net/) loads per-directory environment variables when you `cd` into a project. himitsubako ships a helper that writes a managed block into your `.envrc` so every key in `.secrets.enc.yaml` becomes an environment variable automatically.

This is the highest-convenience workflow for projects that use the SOPS backend: `cd` into the project, every secret is in `os.environ`, your code and any shell tool can read it with no library calls at all.

## How `hmb init` wires direnv up

When you run `hmb init`, himitsubako writes a `.envrc` (if one does not already exist) containing a managed block delimited by start and end markers:

```sh
# --- himitsubako managed block (do not edit between markers) ---
eval "$(sops --decrypt .secrets.enc.yaml | yq -o shell)"
# --- end himitsubako managed block ---
```

Run `direnv allow` once to approve the file:

```sh
direnv allow
```

Subsequent `cd` into the project will auto-load every top-level key in `.secrets.enc.yaml` as an environment variable.

## Automatic refresh on `hmb set`

`hmb set` refreshes the managed block best-effort after a successful write when the default backend is SOPS. The call succeeds even if the refresh fails (e.g., write-protected `.envrc`); the refresh failure is surfaced as a stderr warning so direnv does not silently go stale.

## Manual refresh

If you hand-edit `.envrc`, delete the managed block by accident, or want to be sure the block matches the current secrets file after a rotate, run:

```sh
hmb direnv-export
```

This regenerates the managed block between the markers and leaves the rest of `.envrc` alone.

## Marker format

Everything between the two marker lines is considered himitsubako-managed and will be **overwritten** on every regeneration. Everything outside the markers is preserved. A typical `.envrc` might look like:

```sh
# Project-specific PATH additions
PATH_add bin

# --- himitsubako managed block (do not edit between markers) ---
eval "$(sops --decrypt .secrets.enc.yaml | yq -o shell)"
# --- end himitsubako managed block ---

# Local-only overrides after the block win because they run later.
export DEBUG=1
```

## Safety rails

Two defenses against subtle misuse:

- **Duplicate-marker refusal.** If `.envrc` contains more than one start marker or more than one end marker (typically from a bad merge), `update_envrc` refuses to write and raises `BackendError`, directing the user to resolve the duplicates by hand. Overwriting would silently merge the two blocks and almost always corrupts the file.
- **shlex-quoted secrets path.** The `secrets_file` path is `shlex.quote`d before interpolation into the eval line, so a path with spaces, dollar signs, or backticks cannot break out of the eval and execute arbitrary code. A unit regression test asserts this for all three injection shapes.

## Troubleshooting

### `direnv: error .envrc is blocked`

Run `direnv allow` after every change to `.envrc`. This is direnv's default security posture, not a himitsubako issue.

### Secrets are stale after editing `.secrets.enc.yaml` directly

Run `hmb direnv-export` to force a refresh, or `cd` out and back in. The managed block uses `sops --decrypt` at eval time so it always reads the current file state.

### `BackendError: .envrc contains multiple start markers`

You have two copies of the managed block, probably from a merge. Open `.envrc`, delete all but one copy (or delete both and run `hmb direnv-export`), then commit the fix.

### I want to keep my `.envrc` out of git

Add `.envrc` to `.gitignore`. himitsubako is agnostic; `.envrc` is a local convenience, not part of the project contract. Only `.sops.yaml`, `.himitsubako.yaml`, and `.secrets.enc.yaml` need to be committed for the project to reproduce.
