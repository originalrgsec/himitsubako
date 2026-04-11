# Bitwarden CLI backend

The bitwarden-cli backend stores credentials in your Bitwarden vault by shelling out to the `bw` system binary. It has **no Python pip dependency** — the Bitwarden SDK is deliberately excluded (see [Why not the Bitwarden SDK?](#why-not-the-bitwarden-sdk)).

## When to use it

- You already pay for Bitwarden and want your developer secrets to live alongside your personal passwords.
- You want credentials that survive laptop loss and are accessible from any device where you can install the Bitwarden CLI.
- You want MFA-gated access without building MFA into himitsubako itself.

## Requirements

- The Bitwarden **Password Manager CLI** (`bw`) installed on your PATH. It is GPL-3.0, safe to invoke as a subprocess under the [External CLI Tool Invocation exemption](https://bitwarden.com/download/) in the project's license policy.
- An **unlocked session**, surfaced via the `BW_SESSION` environment variable by default. The backend runs in "strict mode" by default and does **not** prompt for the master password.

## Configuration

```yaml
default_backend: bitwarden-cli
bitwarden:
  folder: my-project        # Bitwarden folder to store items under
  bin: null                  # optional: absolute path to `bw`
  unlock_command: null       # optional: shell command that prints the master password
```

### Three operating modes

1. **Strict (default, recommended).** `BW_SESSION` must be set in the environment; the backend never prompts. Right for library use from non-interactive processes.

    ```sh
    export BW_SESSION="$(bw unlock --raw)"
    hmb get GITHUB_TOKEN
    ```

2. **Pinned binary** (`bin` argument or `HIMITSUBAKO_BW_BIN`). Bypasses PATH lookup. Mitigates PATH-hijack attacks on `bw`.

    ```yaml
    bitwarden:
      bin: /opt/bitwarden/bw
    ```

3. **Shell-out unlock** (`unlock_command`). When `BW_SESSION` is absent, the backend runs the configured command, captures stdout as the master password, and pipes it to `bw unlock --raw` to obtain a session token used in-memory only. The token is never written to disk and never logged.

    ```yaml
    bitwarden:
      unlock_command: "security find-generic-password -s bw-master -w"
    ```

    The unlock command must be trustworthy — it runs with your shell privileges and handles the master password. The threat model (T-022) treats an unsafe `unlock_command` as an accepted residual risk.

## Why not the Bitwarden SDK?

The Bitwarden **Secrets Manager SDK** (`bitwarden-sdk` on PyPI) is distributed under the Bitwarden SDK License Agreement v1, which is **not OSI-approved** and contains field-of-use clauses incompatible with MIT distribution. himitsubako is MIT-licensed, so the SDK is a non-starter as a pip dependency.

The Bitwarden **Password Manager CLI** (`bw`, separate from the SDK) is GPL-3.0, which does allow subprocess invocation without contaminating the caller's license. That is the integration himitsubako ships.

This decision is documented in the project ADR (`ADR-12`) and cross-referenced in the [`allowed-licenses.md`](https://github.com/originalrgsec/himitsubako) policy.

## Capabilities

- `get(key)` — `bw get item KEY` returning the `notes` field of the matched item.
- `set(key, value)` — `bw create item` with JSON piped via stdin so the plaintext value never reaches argv (T-003 mitigation).
- `delete(key)` — `bw delete item KEY`.
- `list_keys()` — `bw list items --folderid <folder>` returning item names.

All subprocesses run with a 30-second timeout.

## stderr redaction

Bitwarden's CLI occasionally echoes the session token verbatim in error strings. The backend runs every stderr string through a base64-token redaction pass (`[A-Za-z0-9+/=]{40,}` becomes `[REDACTED]`) before interpolating it into a `BackendError.detail` field. A unit regression test pins this behavior so the redaction cannot be refactored away.

## Minimal working example

```sh
bw login
export BW_SESSION="$(bw unlock --raw)"

cat > .himitsubako.yaml <<'EOF'
default_backend: bitwarden-cli
bitwarden:
  folder: my-project
EOF

hmb set GITHUB_TOKEN --value "ghp_xxxxxxxxxxxxxxxxxxxx"
hmb get GITHUB_TOKEN | cat
hmb list
hmb delete GITHUB_TOKEN --force
```

## Threat model summary

- **T-003 — value leak via argv.** Mitigated by piping JSON via stdin on `set`.
- **T-005 — `bw` binary PATH hijack.** Mitigated by the pinned `bin` path (`HIMITSUBAKO_BW_BIN` > `bin` config > `PATH` lookup).
- **T-007 — `BW_SESSION` visible in process env.** Accepted residual risk, documented. Strict mode is the recommended default so the session is set by the user, not by the library.
- **T-022 — unsafe `unlock_command`.** Accepted residual risk. The command runs with shell privileges; the user is responsible for what they point it at.
- **Bitwarden CLI stderr token leak.** Mitigated by the base64-token redaction pass before raising `BackendError`. Regression-guarded by a unit test.

See [Security](../security.md) for the user-facing summary.
