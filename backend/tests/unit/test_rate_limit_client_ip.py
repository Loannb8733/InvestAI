"""The rate-limit key must be the real client IP, not a spoofable header value.

A client controls the left of X-Forwarded-For; each trusted proxy appends the
address it received the request from. So the true client is TRUSTED_PROXY_HOPS
entries from the right — reading the leftmost value lets an attacker forge a fresh
key per request and bypass the limiter.
"""

from starlette.datastructures import Headers

from app.core.config import settings
from app.core.rate_limit import _get_real_client_ip


class _Req:
    def __init__(self, headers, client_host="10.0.0.1"):
        self.headers = Headers(headers)
        self.client = type("C", (), {"host": client_host})() if client_host else None


def test_takes_rightmost_hop_for_render_default(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    # Client spoofs 1.2.3.4 on the left; Render appends the true client on the right.
    req = _Req({"X-Forwarded-For": "1.2.3.4, 203.0.113.9"})
    assert _get_real_client_ip(req) == "203.0.113.9"


def test_single_entry_is_used_verbatim(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    req = _Req({"X-Forwarded-For": "203.0.113.9"})
    assert _get_real_client_ip(req) == "203.0.113.9"


def test_two_trusted_hops_reads_two_from_right(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 2)
    # Cloudflare -> Render -> app: real client is 2 from the right.
    req = _Req({"X-Forwarded-For": "spoof, 203.0.113.9, 172.16.0.1"})
    assert _get_real_client_ip(req) == "203.0.113.9"


def test_short_chain_clamps_without_indexerror(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 3)
    req = _Req({"X-Forwarded-For": "203.0.113.9"})
    assert _get_real_client_ip(req) == "203.0.113.9"


def test_falls_back_to_x_real_ip(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    req = _Req({"X-Real-IP": "198.51.100.7"})
    assert _get_real_client_ip(req) == "198.51.100.7"


def test_falls_back_to_peer_when_no_headers(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    req = _Req({}, client_host="10.9.8.7")
    assert _get_real_client_ip(req) == "10.9.8.7"
