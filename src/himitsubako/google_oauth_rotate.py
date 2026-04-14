"""Google OAuth refresh-token rotation flows (HMB-S032).

Two rotation strategies:

1. **Device flow** (default): hit Google's device authorization endpoint,
   print a verification URL + user code, poll the token endpoint until the
   user authorizes or the device_code expires. Works over SSH, in
   containers, and any environment without a browser.

2. **InstalledAppFlow** (`--browser`): run a localhost callback and open
   the browser on the local machine. Faster UX when sitting at a desktop.

Both return the refresh token string. The caller is responsible for
writing it back to the configured storage backend via the existing
GoogleOAuthBackend.set() JSON path.

Requires `google-auth` (always) and `google-auth-oauthlib` (only for
InstalledAppFlow). Install via `pip install himitsubako[google]`.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING

from himitsubako.errors import BackendError

if TYPE_CHECKING:
    from collections.abc import Callable

# Google OAuth 2.0 endpoints for device flow. Pinned to the current documented
# URIs so a DNS typo or copy-paste error surfaces here rather than at runtime.
DEVICE_CODE_ENDPOINT = "https://oauth2.googleapis.com/device/code"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
AUTH_PROVIDER_CERT_URL = "https://www.googleapis.com/oauth2/v1/certs"
DEVICE_CODE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

# Polling parameters — sane defaults if Google's response omits `interval`.
_DEFAULT_POLL_INTERVAL = 5
_MAX_POLL_SECONDS = 600
# Cap the poll interval so a server that keeps returning slow_down cannot
# inflate the interval without bound. The deadline loop already guarantees
# termination; this just keeps a single sleep from blocking for long.
_MAX_POLL_INTERVAL = 30


@dataclass(frozen=True)
class DeviceFlowResult:
    """Refresh token plus the client_id/secret that produced it.

    Returned as a single object so callers do not need to re-read the
    unchanged client credentials from storage to rebuild the JSON blob.
    """

    refresh_token: str


def run_device_flow(
    client_id: str,
    client_secret: str,
    scopes: list[str],
    *,
    emit: Callable[[str], None] | None = None,
    http_post: Callable[[str, dict[str, str]], dict[str, object]] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> DeviceFlowResult:
    """Run the OAuth 2.0 device authorization grant. Returns the new refresh token.

    The `emit`, `http_post`, `sleep`, and `now` hooks are injectable for
    testability. Production code uses the stdlib urllib-based defaults.
    """
    post = http_post or _default_post
    write = emit or _default_emit

    # 1. Request a device code.
    device_response = post(
        DEVICE_CODE_ENDPOINT,
        {"client_id": client_id, "scope": " ".join(scopes)},
    )
    device_code = str(device_response["device_code"])
    user_code = str(device_response["user_code"])
    verification_url = str(
        device_response.get("verification_url") or device_response.get("verification_uri")
    )
    interval = _coerce_int(device_response.get("interval"), _DEFAULT_POLL_INTERVAL)
    expires_in = _coerce_int(device_response.get("expires_in"), _MAX_POLL_SECONDS)

    # 2. Present the code to the user.
    write(f"Open this URL on any device: {verification_url}")
    write(f"Enter the code: {user_code}")
    write(f"Waiting for authorization (poll interval {interval}s, expires in {expires_in}s)...")

    # 3. Poll the token endpoint until the user approves or the code expires.
    deadline = now() + min(expires_in, _MAX_POLL_SECONDS)
    while now() < deadline:
        sleep(interval)
        # Re-check the deadline after sleeping — a long sleep under slow_down
        # pressure can push us past the window while still inside the loop.
        if now() >= deadline:
            break
        token_response = post(
            TOKEN_ENDPOINT,
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "device_code": device_code,
                "grant_type": DEVICE_CODE_GRANT_TYPE,
            },
        )
        error = token_response.get("error")
        if error is None:
            refresh_token = token_response.get("refresh_token")
            if not isinstance(refresh_token, str) or not refresh_token:
                raise BackendError(
                    "google-oauth",
                    "token endpoint returned success but no refresh_token. "
                    "Ensure the OAuth client is configured with offline access.",
                )
            return DeviceFlowResult(refresh_token=refresh_token)

        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval = min(interval + 5, _MAX_POLL_INTERVAL)
            continue
        if error == "access_denied":
            raise BackendError(
                "google-oauth",
                "user denied the authorization request. "
                "Re-run `hmb rotate` and approve the consent screen.",
            )
        if error == "expired_token":
            raise BackendError(
                "google-oauth",
                "device code expired before authorization completed. Re-run `hmb rotate`.",
            )
        # Any other error — most commonly invalid_client, which happens when
        # the GCP project isn't configured for device flow — surface the
        # remediation hint pointing at --browser.
        description = token_response.get("error_description") or ""
        raise BackendError(
            "google-oauth",
            f"device flow rejected by Google: {error}. {description} "
            "This commonly means your GCP project is not configured for "
            "device flow. Retry with `hmb rotate <credential> --browser` "
            "to use the InstalledAppFlow instead.",
        )

    raise BackendError(
        "google-oauth",
        "device flow timed out without authorization. Re-run `hmb rotate`.",
    )


def run_installed_app_flow(
    client_id: str,
    client_secret: str,
    scopes: list[str],
) -> DeviceFlowResult:
    """Run InstalledAppFlow (localhost redirect). Returns the new refresh token.

    Requires `google-auth-oauthlib`. This path opens a browser on the local
    machine and binds a localhost callback server; it is the right choice
    when the user is sitting at a desktop and has a graphical browser.
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:  # pragma: no cover — import guard
        raise BackendError(
            "google-oauth",
            "google-auth-oauthlib is not installed. Install with: pip install himitsubako[google]",
        ) from exc

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": TOKEN_ENDPOINT,
            "auth_provider_x509_cert_url": AUTH_PROVIDER_CERT_URL,
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes)
    creds = flow.run_local_server(port=0, open_browser=True)
    refresh_token = getattr(creds, "refresh_token", None)
    if not isinstance(refresh_token, str) or not refresh_token:
        raise BackendError(
            "google-oauth",
            "InstalledAppFlow completed but returned no refresh_token. "
            "Ensure the OAuth client requests offline access.",
        )
    return DeviceFlowResult(refresh_token=refresh_token)


def _coerce_int(value: object, default: int) -> int:
    """Coerce an untrusted JSON value to int, falling back to `default` on failure."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _default_emit(message: str) -> None:
    """Default user-facing output — stderr so stdout stays clean for piping."""
    import sys as _sys

    print(message, file=_sys.stderr)


def _default_post(url: str, fields: dict[str, str]) -> dict[str, object]:
    """POST form-encoded fields, return the JSON response as a dict.

    Google's OAuth endpoints accept form-encoded bodies and return JSON on
    both success (200) and OAuth error (4xx) paths; OAuth errors are
    returned as a normal dict so the polling logic can branch on the
    `error` key. True transport failures (DNS, connection refused,
    timeout) are wrapped as BackendError instead of leaking a urllib
    traceback to the caller.

    TLS verification is explicit via `ssl.create_default_context()`,
    which uses the system CA bundle and rejects self-signed certificates.
    """
    body = urllib.parse.urlencode(fields).encode("ascii")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    ssl_context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl_context) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        # OAuth error responses come back as 4xx with a JSON body. Read it
        # and return as a normal result so the polling logic can branch.
        payload = exc.read()
    except urllib.error.URLError as exc:
        raise BackendError(
            "google-oauth",
            f"network error contacting OAuth endpoint {url}: {exc.reason}",
        ) from exc
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackendError(
            "google-oauth",
            f"OAuth endpoint returned non-JSON payload (truncated): {payload[:200]!r}",
        ) from exc
    if not isinstance(parsed, dict):
        raise BackendError(
            "google-oauth",
            f"OAuth endpoint returned non-object payload: {type(parsed).__name__}",
        )
    return parsed
