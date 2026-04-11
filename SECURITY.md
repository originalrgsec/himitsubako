# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.3.x (current) | ✓ |
| 0.2.x | Fix only for CRITICAL severity |
| 0.1.x | No |

himitsubako is alpha software. Until the 1.0 tag lands, only the latest minor version receives routine security patches. `0.2.x` gets CRITICAL-only patches as a courtesy; older versions are unsupported. The supported-versions table will tighten as the project stabilises.

## Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.** Public issues are indexed instantly and a pre-patch disclosure window turns a fixable bug into an exploitable one.

Use GitHub's private vulnerability reporting instead:

1. Go to [the security tab](https://github.com/originalrgsec/himitsubako/security).
2. Click **Report a vulnerability**.
3. Describe the issue, the affected version(s), the impact, and a minimal reproduction.
4. Attach any proof-of-concept code or exploit paths directly.

If GitHub Security Advisories is not available to you, email the maintainer directly via the contact in the repo `README.md`.

## Expected response time

- **Initial acknowledgement:** within 3 business days.
- **Severity assessment:** within 7 business days.
- **Fix or mitigation plan:** within 14 business days of acknowledgement for CRITICAL / HIGH findings; best-effort for MEDIUM / LOW.
- **Coordinated disclosure:** fix commits will be prepared on a private branch, tagged on a new patch release, and published to PyPI before the advisory goes public. Reporters are credited in the advisory unless they request anonymity.

Response times assume the maintainer is not on extended leave. himitsubako is not a funded project; response times are best-effort and will be documented honestly in the advisory if they slip.

## Scope

### In scope

- **Library code.** Any path through `himitsubako` (the Python package) that could leak a secret, bypass a safety gate, corrupt state, execute arbitrary code, or escalate privilege.
- **CLI (`hmb`).** Command parsing, the TTY reveal gate, the confirmation prompt on `hmb delete`, the `hmb init` scaffolding, and the interaction with `~/.config/sops/age/keys.txt`.
- **Backend integrations.** The SOPS, env, keychain, and bitwarden-cli backends. The `BackendRouter` dispatcher.
- **Helpers and integrations.** The `HimitsubakoSettingsSource` pydantic-settings source, the direnv helper, and the `hmb status` diagnostic.
- **CI and release workflows.** `.github/workflows/ci.yml` and `.github/workflows/release.yml`. Supply-chain vulnerabilities in pinned action SHAs or binary checksums are in scope.

### Out of scope

- **Upstream tools.** Vulnerabilities in `sops`, `age`, `bw`, `keyring`, `direnv`, or the operating-system keystores (`Security.framework`, `libsecret`, `kwallet`, etc.) should be reported to their respective maintainers. himitsubako invokes these tools but does not re-implement them.
- **OS-level weaknesses.** Anything that assumes an attacker already has arbitrary code execution as the user — at that point every credential store on the system is compromised.
- **Misconfiguration without a vulnerable code path.** A user who commits a plaintext `.env` to a public repo has a security incident, but not a himitsubako vulnerability. A user who removes the TTY reveal gate by editing the source has a security incident, but not a himitsubako vulnerability.
- **Physical access.** If the attacker can read your unlocked laptop's filesystem, every file mode and every cached session is forfeit. himitsubako is not a disk-encryption layer.

### Deliberate non-goals

See [`docs/security.md`](docs/security.md) for the user-facing summary of what himitsubako protects against and what it deliberately does not. Loss of the age private key, crash-dump leakage, child-process env inheritance, and enumeration on keychain are all named as deliberate non-goals with rationale.

## Security-sensitive code paths

Regression-guarded defenses (every one is pinned by a unit or integration test):

- **File mode 0600** on `.secrets.enc.yaml` after every write (`TestSopsBackendFilePermissions`).
- **`--filename-override`** passed to `sops --encrypt` so creation_rules apply to the real target (`TestSopsBackendFilenameOverride`).
- **Subprocess timeouts** on every sops invocation (`TestSopsBackendTimeout`).
- **TTY reveal gate** on `hmb get` (`TestGetRevealGate`).
- **Keychain insecure-backend deny-list** with MRO walk (`test_keychain_backend.py::TestDenyList`).
- **Bitwarden stderr token redaction** (`test_bitwarden_backend.py::TestStderrRedaction`).
- **Bitwarden value-via-stdin** (the set() path never puts the value on argv).
- **direnv duplicate-marker refusal** (integration test in `test_direnv_real.py`).
- **direnv shlex-quoted secrets path** (integration test in `test_direnv_real.py`).

A security fix that bypasses any of these defenses without replacing them is a regression. Every pin has a test; every test is enforced by CI.
