# pydantic-settings integration

himitsubako ships a [`pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) source (`HimitsubakoSettingsSource`) that plugs your `.himitsubako.yaml` configuration into any `BaseSettings` class. This is the right integration point if you already use pydantic-settings for application configuration — no branching in your app code, one lookup surface for everything.

## Install

```sh
pip install 'himitsubako[pydantic-settings]'
```

The extra declares a pin on `pydantic-settings>=2.13,<3.0`.

## Basic usage

```python
from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from himitsubako.pydantic import HimitsubakoSettingsSource


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    devto_api_key: str = Field(...)
    github_token: str = Field(...)
    log_level: str = "info"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            env_settings,
            HimitsubakoSettingsSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )
```

With the source list above, a call like `AppSettings()` resolves each field by walking the source tuple left-to-right until it finds a value. `HimitsubakoSettingsSource` sits after `env_settings` so a transient `DEVTO_API_KEY` env var wins over the persisted secret, which is usually what you want in CI.

## Source precedence

The default order himitsubako recommends is:

```
init_settings > env_settings > HimitsubakoSettingsSource > dotenv_settings > file_secret_settings
```

- **init kwargs** — explicit constructor overrides, highest priority for tests.
- **env vars** — for one-shot overrides in CI / containers.
- **himitsubako** — the persisted secret store (SOPS, keychain, bitwarden-cli, or any `BackendRouter` configuration).
- **dotenv** — `.env` file for local development defaults that you are willing to commit (non-secret).
- **file secret** — pydantic-settings' own file-per-secret mechanism, for Docker secrets and similar.
- **defaults** — the values declared on the `BaseSettings` class itself.

You are free to reorder. The one constraint is: if you put `HimitsubakoSettingsSource` above `env_settings`, environment-variable overrides stop working, which is almost always wrong for CI and containers.

## Key naming

`HimitsubakoSettingsSource` uses the field name as the lookup key. pydantic-settings normalizes field names to uppercase for env-like lookups, so a field `devto_api_key` becomes `DEVTO_API_KEY` when querying himitsubako. This matches the convention most users follow for SOPS and env backends and avoids awkward case mismatches.

If your field name and your stored key name need to disagree, use a `Field(validation_alias=...)` to declare the mapping explicitly:

```python
devto_api_key: str = Field(..., validation_alias="DEV_TO_KEY")
```

## Working directory

`HimitsubakoSettingsSource` calls `find_config(Path.cwd())` internally. If your application starts from an arbitrary working directory (a systemd service, a container entrypoint), either `chdir` into the project root first or construct the source with an explicit config path — the constructor accepts a `project_dir` kwarg.

```python
HimitsubakoSettingsSource(
    AppSettings,
    project_dir=Path("/opt/myapp"),
)
```

## Fallback behavior

If no `.himitsubako.yaml` is found, `HimitsubakoSettingsSource` falls back to the env-variable backend (same as the high-level `himitsubako.get()` helper). This means a container with no config file but injected env vars still resolves cleanly, without a config-not-found exception at startup.

## Worked example: mixed SOPS + env

```yaml
# .himitsubako.yaml
default_backend: sops
sops:
  secrets_file: .secrets.enc.yaml
env:
  prefix: CI_
credentials:
  "CI_*":
    backend: env
```

```python
class AppSettings(BaseSettings):
    devto_api_key: str
    github_token: str
    ci_run_id: str | None = None

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                                   dotenv_settings, file_secret_settings):
        return (
            init_settings,
            env_settings,
            HimitsubakoSettingsSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )
```

With this setup, `AppSettings().devto_api_key` decrypts from SOPS, `AppSettings().ci_run_id` reads from `os.environ["CI_RUN_ID"]`, and both resolutions go through the same `BaseSettings()` call.
