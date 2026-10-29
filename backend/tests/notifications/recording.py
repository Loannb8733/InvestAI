import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from email import message_from_string
from email.header import decode_header, make_header
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from httpx import AsyncClient

from tests.http_stubs import HttpStub

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
VOLATILE_KEYS = frozenset({"created_at", "updated_at"})
TELEGRAM = "api.telegram.org"


def plain(value: Any, ids: dict[str, str]) -> Any:
    """Valeur comparable d'une exécution à l'autre : identifiants numérotés, dates en ISO, flottants arrondis."""
    if isinstance(value, dict):
        return {k: "<volatile>" if k in VOLATILE_KEYS else plain(v, ids) for k, v in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [plain(v, ids) for v in value]
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return plain(str(value), ids)
    if isinstance(value, str):
        return UUID_RE.sub(lambda m: ids.setdefault(m.group(0), f"<id-{len(ids)}>"), value)
    return value


class Telegram:
    """Faux Bot API Telegram : répond comme le vrai, ou en erreur quand ``failing``, et garde chaque appel."""

    def __init__(self, stub: HttpStub) -> None:
        self.calls: list[dict[str, Any]] = []
        self.failing = False
        stub.on(TELEGRAM, self._answer)

    def _answer(self, request: httpx.Request) -> httpx.Response:
        self.calls.append({"method": request.url.path.rsplit("/", 1)[-1], "body": json.loads(request.content or b"{}")})
        if self.failing:
            return httpx.Response(
                400, json={"ok": False, "description": "Bad Request: chat not found"}, request=request
            )
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}}, request=request)

    def drain(self) -> list[dict[str, Any]]:
        calls, self.calls = self.calls, []
        return calls


class Mailbox:
    """Faux serveur SMTP : chaque message envoyé est gardé, décodé en en-têtes et parties."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def smtp(self, *args: Any, **kwargs: Any) -> "Mailbox":
        return self

    def __enter__(self) -> "Mailbox":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def starttls(self, **kwargs: Any) -> None:
        return None

    def login(self, user: str, password: str) -> None:
        return None

    def sendmail(self, sender: str, to: str, raw: str) -> None:
        message = message_from_string(raw)
        parts = []
        for part in message.walk():
            if part.is_multipart():
                continue
            filename = part.get_filename()
            body = part.get_payload(decode=True) or b""
            parts.append(
                {"type": part.get_content_type(), "attachment": filename}
                if filename
                else {"type": part.get_content_type(), "text": body.decode(part.get_content_charset() or "utf-8")}
            )
        headers = {k: str(make_header(decode_header(v))) for k, v in message.items() if k.lower() != "content-type"}
        self.sent.append({"envelope": [sender, to], "headers": headers, "parts": parts})

    def drain(self) -> list[dict[str, Any]]:
        sent, self.sent = self.sent, []
        return sent


class Recorder:
    """Compare chaque prise à son fichier golden, ou l'écrit quand GOLDEN_UPDATE=1."""

    def __init__(self, client: AsyncClient | None = None, telegram: Telegram | None = None) -> None:
        self.client = client
        self.telegram = telegram
        self.ids: dict[str, str] = {}
        self.mismatches: list[str] = []

    def check(self, name: str, value: Any) -> None:
        rendered = json.dumps(plain(value, self.ids), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        path = GOLDEN_DIR / f"{name}.json"
        if UPDATE or not path.exists():
            GOLDEN_DIR.mkdir(exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
        elif path.read_text(encoding="utf-8") != rendered:
            self.mismatches.append(name)

    async def shot(
        self,
        name: str,
        method: str,
        url: str,
        headers: dict[str, str],
        body: Any = None,
        content: bytes | None = None,
    ) -> Any:
        assert self.client is not None
        response = await self.client.request(method, url, headers=headers, json=body, content=content)
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        record: dict[str, Any] = {"status": response.status_code, "body": payload}
        if self.telegram is not None:
            record["telegram"] = self.telegram.drain()
        self.check(name, record)
        return payload
