# Public API Changes — v0.8.0

This file is the canonical record of public-API changes between consecutive
himitsubako releases. Downstream consumers (open-workspace-builder,
home-ops, outbound-pipeline, ingest-pipeline, volcanix-papers,
content-production) read this file to absorb breaking changes in their next
sprint.

## v0.7.0 → v0.8.0

### Removed

- **`himitsubako.backends.google_oauth.GoogleOAuthBackend.credential_name`**
  (property) — removed without deprecation.
  - **Why:** speculative API added in HMB-S030 (Sprint 7) for potential
    consumer use, but no caller materialized in any internal repo. Property
    accessor for `_credential_name` (the private attribute is still used
    extensively inside the class).
  - **Migration:** consumers that need the credential name already have it
    at the call site — they passed it to `BackendRouter.resolve()` or read
    it from `.himitsubako.yaml`. If a consumer has stored the
    `GoogleOAuthBackend` instance and now needs the name, they can use the
    backing attribute via `backend._credential_name` (note the leading
    underscore — this becomes a private-attribute-access if used) or
    re-thread the original credential name through their own code.
  - **Surface affected:** `from himitsubako.backends.google_oauth import
    GoogleOAuthBackend; b.credential_name` — search for `.credential_name`
    on a `GoogleOAuthBackend` instance.

### Renamed

(none this release)

### Signature Changed

(none this release)

### Internal-only changes (no migration needed)

These do not affect consumers but are listed for transparency:

- `_build_envrc` removed from `himitsubako.cli.init` (private; was a
  legacy v0.1.0 forwarder with no remaining callers).
- `HimitsubakoSettingsSource.prepare_field_value` override removed
  (private; was an identity pass-through that matched the
  `pydantic_settings.PydanticBaseSettingsSource` base-class default).

### Behaviour changes worth noting (no API change)

These are not symbol changes but consumers reading error strings should
be aware:

- `BackendError.detail` strings from `SopsBackend._decrypt`,
  `SopsBackend._encrypt`, `hmb rotate-key`, and the Google OAuth flows now
  pass through the redaction helper. If a consumer was matching on the
  exact pre-redaction stderr substring (unlikely), tests need updating.
- `bitwarden.unlock_command` is now parsed with `shlex.split()` and run
  with `shell=False`. Pipelines and shell substitutions in the config
  value no longer execute; wrap them in a shell script. The common
  `pass show <path>` shape continues to work unchanged.
- `hmb rotate-key --new-key` now uses `click.Path(exists=True)` so
  click handles the existence check at parse time. The exit code for a
  missing file changes from 1 (ClickException) to 2 (click parse error).
