# Keychain backend

The keychain backend stores credentials in the OS-native secret store via the [`keyring`](https://pypi.org/project/keyring/) library. On macOS this is the Keychain (backed by `Security.framework`); on Linux, it can be `gnome-keyring`, `kwallet`, or any other backend `keyring.get_keyring()` resolves.

## When to use it

- **Personal long-lived credentials** that survive repo deletion (GitHub OAuth, Bitwarden-style PATs used outside of Bitwarden, SSH key passphrases).
- **macOS-primary workflows** where Keychain is the obvious source of truth.
- **Anywhere you want "not in git" to be a hard guarantee** — nothing on disk in plaintext, nothing encrypted in the repo, nothing readable without the user's session.

## Requirements

- The `[keychain]` optional extra: `pip install 'himitsubako[keychain]'`. Without it, calling any keychain backend operation raises `BackendError` with a clear install hint.
- On Linux, a usable keyring daemon (gnome-keyring, kwallet, or a properly configured secret-service implementation). himitsubako **refuses** to run against `Null`, `PlaintextKeyring`, `EncryptedKeyring`, or `fail.Keyring` — see [Insecure backend deny-list](#insecure-backend-deny-list).

## Configuration

```yaml
default_backend: keychain
keychain:
  service: my-project     # keyring service name; defaults to "himitsubako"
```

The `service` name is the string passed to `keyring.get_password(service, key)` and `keyring.set_password(service, key, value)`. Pick something distinctive per project so entries do not collide in the system keyring UI.

## Capabilities

- `get(key)` — `keyring.get_password(service, key)`.
- `set(key, value)` — `keyring.set_password(service, key, value)`.
- `delete(key)` — `keyring.delete_password(service, key)`. Raises `SecretNotFoundError` when the key does not exist (so `hmb delete --missing-ok` works correctly).
- `list_keys()` — **raises `BackendError`**. The `keyring` public API does not expose enumeration. Returning an empty list would silently mislead callers; an explicit error is more honest. `hmb list` catches this and prints a friendly message pointing users at their project's secrets registry.
- `check_availability()` — the `hmb status` ping, added in HMB-S019. Imports `keyring`, calls `get_keyring()`, walks the MRO against the deny-list. Does not touch any stored credential.

## Insecure backend deny-list

On a misconfigured Linux host, `keyring.get_keyring()` can silently fall back to `Null` (drops writes on the floor) or `PlaintextKeyring` (stores secrets in the clear under `~/.local/share/python_keyring/`). Both would be catastrophic for a credential manager, so the keychain backend rejects them. The check walks the resolved class MRO, so a subclass like `class SafeWrapper(PlaintextKeyring)` cannot bypass the gate by renaming the leaf class.

When the deny-list hits, you get:

```
keychain: unavailable (keyring resolved to insecure backend 'PlaintextKeyring' (MRO matches ['PlaintextKeyring']); install gnome-keyring (Linux), use macOS Keychain (Darwin), or set keyring's preferred backend explicitly)
```

Fix it by installing a real keyring daemon (`gnome-keyring` or `kwallet` on Linux), ensuring the D-Bus session is running for your user, or setting `keyring.set_keyring(...)` in a startup hook before any himitsubako call.

## Minimal working example

```sh
pip install 'himitsubako[keychain]'

cat > .himitsubako.yaml <<'EOF'
default_backend: keychain
keychain:
  service: my-project
EOF

hmb set GITHUB_OAUTH_TOKEN
# Value: (hidden prompt)
hmb get GITHUB_OAUTH_TOKEN | cat
hmb delete GITHUB_OAUTH_TOKEN
```

## Threat model summary

- **T-020 — insecure keyring backend.** Mitigated by the MRO-walking deny-list above (M-015).
- **T-021 — missing keyring optional dependency.** Mitigated by converting `ImportError` to a `BackendError` with a clear install hint.
- **Enumeration.** Intentionally unsupported. This is neither a security property nor a leak, just an API limitation of `keyring`. `hmb list` prints a friendly message and exits 0.

See [Security](../security.md) for the user-facing summary.
