"""Debug-only endpoints must not be reachable in production.

The /transactions/debug/* endpoints expose internal FIFO traces / raw metrics and
are guarded only by user auth. In production they should 404 so internals are
never exposed on the public surface.
"""

import pytest
from fastapi import HTTPException

from app.api.deps import require_debug_enabled
from app.core.config import settings


def test_require_debug_enabled_blocks_production(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "DEBUG", False)
    with pytest.raises(HTTPException) as exc:
        require_debug_enabled()
    assert exc.value.status_code == 404


def test_require_debug_enabled_allows_non_production(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "DEBUG", False)
    # No raise outside production.
    assert require_debug_enabled() is None


def test_require_debug_enabled_allows_prod_env_with_debug_on(monkeypatch):
    # is_production is False when DEBUG is on, so the guard must allow it.
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "DEBUG", True)
    assert require_debug_enabled() is None
