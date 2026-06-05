"""Sentry scrubbing helpers.

Sentry's FastApiIntegration captures request/response bodies and headers by
default, which can leak JWT bearer tokens, login credentials, exchange API
keys, MFA TOTP codes, and similar secrets to the Sentry project. This module
provides ``before_send`` (and ``before_send_transaction``) callbacks that strip
those fields before any event leaves the process.

Approach:
- Redact a known set of sensitive header names (Authorization, Cookie, …).
- Walk request.data / extra payloads recursively and redact any key whose name
  matches a sensitive pattern (password, secret, token, api_key, mfa_code, …).
- Truncate long string values to keep payloads bounded.

The redaction is conservative: when in doubt, we redact. Sentry events are for
debugging — losing a noisy field is fine, leaking a credential is not.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, MutableMapping, Optional

_REDACTED = "[redacted]"
_MAX_STR_LEN = 1024

_SENSITIVE_HEADER_NAMES = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-cron-token",
        "x-csrf-token",
        "x-forwarded-authorization",
        "proxy-authorization",
    }
)

# Substring patterns matched case-insensitively against any dict key.
_SENSITIVE_KEY_PATTERNS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "privatekey",
    "passphrase",
    "mfa",
    "totp",
    "otp",
    "fernet",
    "encrypted",
    "credential",
    "bearer",
    "session",
)

_KEY_PATTERN_RE = re.compile("|".join(re.escape(p) for p in _SENSITIVE_KEY_PATTERNS), re.IGNORECASE)


def _redact_headers(headers: Any) -> Any:
    """Redact known sensitive header names. Accepts dict or list-of-pairs."""
    if isinstance(headers, MutableMapping):
        for key in list(headers.keys()):
            if key.lower() in _SENSITIVE_HEADER_NAMES:
                headers[key] = _REDACTED
        return headers
    if isinstance(headers, list):
        return [
            [k, _REDACTED if isinstance(k, str) and k.lower() in _SENSITIVE_HEADER_NAMES else v] for k, v in headers
        ]
    return headers


def _scrub(value: Any, depth: int = 0) -> Any:
    """Recursively redact sensitive keys and truncate long strings."""
    if depth > 6:  # arbitrary bound to prevent pathological structures
        return _REDACTED
    if isinstance(value, MutableMapping):
        for key in list(value.keys()):
            if isinstance(key, str) and _KEY_PATTERN_RE.search(key):
                value[key] = _REDACTED
            else:
                value[key] = _scrub(value[key], depth + 1)
        return value
    if isinstance(value, Mapping):
        # Read-only mapping: build a new dict
        return {
            k: _REDACTED if isinstance(k, str) and _KEY_PATTERN_RE.search(k) else _scrub(v, depth + 1)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(v, depth + 1) for v in value]
    if isinstance(value, tuple):
        return tuple(_scrub(v, depth + 1) for v in value)
    if isinstance(value, str) and len(value) > _MAX_STR_LEN:
        return value[:_MAX_STR_LEN] + "…[truncated]"
    return value


def scrub_event(event: Optional[dict], _hint: Optional[dict] = None) -> Optional[dict]:
    """Sentry ``before_send`` callback: redact secrets in-place before sending."""
    if event is None:
        return None
    request = event.get("request")
    if isinstance(request, MutableMapping):
        if "headers" in request:
            request["headers"] = _redact_headers(request["headers"])
        if "cookies" in request:
            request["cookies"] = _REDACTED
        if "data" in request:
            request["data"] = _scrub(request["data"])
        if "query_string" in request and isinstance(request["query_string"], str):
            # Tokens sometimes leak via ?token=… URLs
            if any(p in request["query_string"].lower() for p in _SENSITIVE_KEY_PATTERNS):
                request["query_string"] = _REDACTED
    for k in ("extra", "contexts", "tags"):
        if k in event:
            event[k] = _scrub(event[k])
    return event
