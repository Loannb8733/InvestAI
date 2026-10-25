import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from httpx import AsyncClient

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
VOLATILE_KEYS = frozenset({"created_at", "updated_at", "completed_at"})
BASE = "/api/v1/crowdfunding"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


def _plain(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {k: "<volatile>" if k in VOLATILE_KEYS else _plain(v, ids) for k, v in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [_plain(v, ids) for v in value]
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, str):
        return UUID_RE.sub(lambda m: ids.setdefault(m.group(0), f"<id-{len(ids)}>"), value)
    return value


class Recorder:
    def __init__(self, client: AsyncClient) -> None:
        self.client = client
        self.ids: dict[str, str] = {}
        self.mismatches: list[str] = []

    def compare(self, name: str, actual: Any) -> None:
        path = GOLDEN_DIR / f"{name}.json"
        rendered = json.dumps(_plain(actual, self.ids), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        if UPDATE or not path.exists():
            GOLDEN_DIR.mkdir(exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
        elif path.read_text(encoding="utf-8") != rendered:
            self.mismatches.append(name)

    async def shot(self, name: str, method: str, url: str, headers: dict[str, str], body: Any = None, **kw: Any) -> Any:
        response = await self.client.request(method, url, headers=headers, json=body, **kw)
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        self.compare(name, {"status": response.status_code, "body": payload})
        return payload
