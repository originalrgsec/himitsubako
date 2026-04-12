---
hide:
  - navigation
  - toc
---

<div class="rg-hero" markdown>

<img src="assets/images/profile-avatar.jpg" alt="originalrgsec" class="rg-hero__avatar">

<p class="rg-hero__tagline">
  Multi-backend credential abstraction for solo Python developers.
</p>

<p class="rg-hero__sub">
  himitsubako (秘密箱, "secret box") gives you one consistent Python API and CLI for credentials across SOPS+age, macOS Keychain, Bitwarden CLI, direnv, and environment variables. Named after Hakone puzzle boxes, which open through a sequence of sliding moves rather than a single key.
</p>

<div class="rg-hero__actions">
  <a href="getting-started/" class="rg-btn rg-btn--primary">Get Started</a>
  <a href="why-not/" class="rg-btn rg-btn--secondary">Why Not ...?</a>
</div>

</div>

<div class="rg-section" markdown>

<p class="rg-section__title">The problem is not your secrets manager. The problem is you have five of them.</p>

<p class="rg-section__desc">
  API keys in <code>.env</code> files. OAuth tokens in macOS Keychain. Deploy credentials in Bitwarden. Database passwords in SOPS. Each project wires its own approach and none of them talk to each other. himitsubako routes each credential to the backend that makes sense for it and gives your code a single interface to all of them.
</p>

</div>

<div class="rg-features" markdown>

<div class="rg-feature" markdown>
<div class="rg-feature__icon"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#D4A017" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></div>
<div class="rg-feature__title">Encrypted Secrets in Git</div>
<div class="rg-feature__desc">
SOPS + age is the primary backend. Commit <code>.secrets.enc.yaml</code> to a public repo without leaking values. Readable diffs, single-command key rotation, and append-only audit logging for every rotate operation.
</div>
</div>

<div class="rg-feature" markdown>
<div class="rg-feature__icon"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#D4A017" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg></div>
<div class="rg-feature__title">Per-Credential Routing</div>
<div class="rg-feature__desc">
One project can keep its OAuth token in macOS Keychain and its deploy key in SOPS. The <code>BackendRouter</code> dispatches each credential to the right backend via <code>.himitsubako.yaml</code>, transparently to your code.
</div>
</div>

<div class="rg-feature" markdown>
<div class="rg-feature__icon"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#D4A017" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg></div>
<div class="rg-feature__title">Five Backends, One Interface</div>
<div class="rg-feature__desc">
SOPS+age for portable encryption. macOS Keychain for long-lived personal tokens. Bitwarden CLI for credentials you already manage there. Environment variables for 12-factor and CI. direnv for automatic shell loading on <code>cd</code>. All accessed through the same Python API and CLI.
</div>
</div>

<div class="rg-feature" markdown>
<div class="rg-feature__icon"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#D4A017" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></div>
<div class="rg-feature__title">Safety Rails by Default</div>
<div class="rg-feature__desc">
<code>hmb get</code> refuses to print secrets to a TTY without <code>--reveal</code>. Encrypted files are written mode 0600. Bitwarden CLI stderr is redacted before surfacing in errors. Subprocess calls have 30-second timeouts. The library is around 1,000 lines of auditable Python.
</div>
</div>

<div class="rg-feature" markdown>
<div class="rg-feature__icon"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#D4A017" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg></div>
<div class="rg-feature__title">pydantic-settings Integration</div>
<div class="rg-feature__desc">
<code>HimitsubakoSettingsSource</code> plugs into pydantic-settings as a first-class source. Declare your credentials as typed model fields and let the source resolve them through the backend router. No manual wiring, no <code>os.environ</code> calls.
</div>
</div>

</div>

<div class="rg-install" markdown>

<p class="rg-install__title">Start using it</p>

```bash
pip install himitsubako
hmb init
```

himitsubako is [available on PyPI](https://pypi.org/project/himitsubako/), [conda-forge](https://github.com/conda-forge/staged-recipes/pull/32938), and [Homebrew](https://github.com/originalrgsec/homebrew-tap).

[Read the getting started guide](getting-started.md){ .rg-btn .rg-btn--primary }

</div>
