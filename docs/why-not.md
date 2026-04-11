# Why not ...?

A short tour of the alternatives. himitsubako is not trying to displace any of these — it is trying to occupy a specific niche they leave open.

## Why not just `.env` files?

`.env` files are fine for local development and containers. They are not fine for:

- **Checking secrets into git.** Even an encrypted `.env.age` commits you to rolling your own encryption boilerplate, a rotation story, and a backup plan. himitsubako's SOPS backend is all three out of the box.
- **Per-credential routing.** A `.env` file is one backend. himitsubako's `BackendRouter` lets you send `GITHUB_OAUTH_TOKEN` to the OS keyring and `DJANGO_SECRET_KEY` to SOPS with no branching in your code.
- **Python library integration.** `.env` files need `python-dotenv` and a load step. himitsubako is a function call (`himitsubako.get(...)`) or a pydantic-settings source.

If your whole project needs is "one file of local dev defaults," `.env` is probably the right answer and himitsubako is overkill.

## Why not HashiCorp Vault?

Vault is the right answer when you have a team, a production fleet, and a compliance requirement. For solo development laptops, it is wildly overbuilt:

- You run a service, not a binary.
- You depend on a token refresh loop.
- You add a daemon process that can fail and wedge your workflow.
- You hand a substantial attack surface to a tool that is solving a problem you do not have yet.

himitsubako is what you use before you need Vault. If you later adopt Vault for production, the Python API is small enough that switching is a one-file diff.

## Why not AWS Secrets Manager / GCP Secret Manager / Azure Key Vault?

Similar reasoning: excellent for production, noisy for local development. You pay per-request, you depend on cloud auth working, and you cannot check anything into git for the next developer. The cloud secret managers are the right production target — himitsubako is the dev-and-bootstrapping story, and the Python API is deliberately minimal so migrating to a cloud secret manager later is simple.

## Why not [teller](https://github.com/tellerops/teller)?

teller is excellent and covers a broader backend matrix than himitsubako. The differences that matter:

- **teller is Go.** If you are a Go developer or want a language-agnostic CLI that shells out, teller is probably a better fit.
- **himitsubako is Python-native.** You can `import himitsubako`, not just shell out to it. That matters if you want programmatic access from Python code, integration with pydantic-settings, or an `AsyncIO`-friendly API in the future.
- **himitsubako ships a threat model and regression guards for its security properties.** teller's defense posture is fine, but himitsubako is explicit about what it protects against and has unit tests pinning each defense.

If you are shopping and teller fits, use teller. himitsubako exists because I wanted a Python-native library, not because teller is wrong.

## Why not [sopsy](https://pypi.org/project/sopsy/) or any of the other "sops wrapper" PyPI packages?

Most of them wrap `sops --decrypt` and call it a day. himitsubako is not "a sops wrapper":

- It has four backends (SOPS, env, keychain, bitwarden-cli), not one.
- It has per-credential routing.
- It has a `direnv` integration.
- It has a `pydantic-settings` source.
- It has a TTY reveal gate and a threat model.

If you really only want to decrypt a sops file from Python, a five-line `subprocess.run(["sops", "-d", path])` does the job and you should not bring a library in for that.

## Why not the Bitwarden Secrets Manager SDK?

The Bitwarden **Secrets Manager SDK** (`bitwarden-sdk` on PyPI) is distributed under the Bitwarden SDK License Agreement v1, which is **not OSI-approved** and contains field-of-use clauses that are incompatible with MIT distribution. himitsubako is MIT-licensed, so pulling in the SDK is a non-starter.

The Bitwarden **Password Manager CLI** (`bw`) is GPL-3.0 and is safe to invoke via subprocess without contaminating the caller's license. That is the integration himitsubako ships — `bw` is invoked as a subprocess, not linked as a library. See [Bitwarden CLI backend → Why not the SDK?](backends/bitwarden-cli.md#why-not-the-bitwarden-sdk) for the full writeup.

## Why `himitsu-bako` and not `secretbox` / `keymaster` / `pyvault`?

秘密箱 (himitsu-bako) literally means "secret box" in Japanese. Himitsu-bako are traditional puzzle boxes from the Hakone region, dating to the 1830s, that open through a sequence of sliding moves rather than a single external key. Secrets accessed through a sequence of moves (age keys, SOPS paths, CLI subcommands, direnv hooks) fit the metaphor better than "another library with 'key' or 'vault' in the name." Also, `keymaster` was taken on PyPI.
