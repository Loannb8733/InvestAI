import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from app.domains.exchanges.connectors.base import ExchangeTrade
from app.domains.exchanges.connectors.kraken.core import KrakenCore

logger = logging.getLogger(__name__)


class KrakenLedgers(KrakenCore):
    async def get_ledgers(  # noqa: C901
        self,
        asset: str | None = None,
        ledger_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        """Écritures du grand livre, toutes catégories confondues, de la plus récente à la plus ancienne."""
        ledgers: list[dict[str, Any]] = []
        offset = 0

        async with httpx.AsyncClient() as client:
            while len(ledgers) < limit:
                uri_path = "/0/private/Ledgers"
                data: dict[str, Any] = {"ofs": offset}

                if asset:
                    data["asset"] = asset
                if ledger_type:
                    data["type"] = ledger_type
                if start_time:
                    data["start"] = int(start_time.timestamp())
                if end_time:
                    data["end"] = int(end_time.timestamp())

                headers = self._sign_request(uri_path, data)

                response = await client.post(
                    f"{self.BASE_URL}{uri_path}",
                    data=data,
                    headers=headers,
                    timeout=30.0,
                )
                result = response.json()

                if result.get("error"):
                    logger.error(f"Ledgers error: {result.get('error')}")
                    break

                ledgers_data = result.get("result", {}).get("ledger", {})

                if not ledgers_data:
                    break

                for ledger_id, entry in ledgers_data.items():
                    if len(ledgers) >= limit:
                        break

                    ledgers.append(
                        {
                            "ledger_id": ledger_id,
                            "refid": entry.get("refid", ""),
                            "time": datetime.fromtimestamp(entry["time"], tz=UTC),
                            "type": entry["type"],
                            "subtype": entry.get("subtype", ""),
                            "aclass": entry.get("aclass", ""),
                            "asset": self._normalize_asset(entry["asset"]),
                            "amount": Decimal(entry["amount"]),
                            "fee": Decimal(entry["fee"]),
                            "balance": Decimal(entry["balance"]),
                        }
                    )

                offset += len(ledgers_data)

                if len(ledgers_data) < 50:
                    break

        return sorted(ledgers, key=lambda x: x["time"], reverse=True)

    async def get_instant_buys(  # noqa: C901
        self, limit: int = 500, ledgers: list[dict[str, Any]] | None = None
    ) -> tuple[list[ExchangeTrade], set[str]]:
        """Achats instantanés : paires de même refid entre une dépense en devise et une réception de crypto.

        Renvoie aussi les refid retenus, pour que les conversions ne les comptent pas une seconde fois.
        """
        trades: list[ExchangeTrade] = []

        if ledgers is None:
            ledgers = await self.get_ledgers(limit=limit * 2)

        by_refid: dict[str, list[dict[str, Any]]] = {}
        for entry in ledgers:
            refid = entry["refid"]
            if refid:
                if refid not in by_refid:
                    by_refid[refid] = []
                by_refid[refid].append(entry)

        fiat_currencies = ["EUR", "USD", "GBP", "CAD", "JPY", "CHF", "AUD"]

        processed_refids: set[str] = set()
        for refid, entries in by_refid.items():
            if refid in processed_refids:
                continue

            spend_entry: dict[str, Any] | None = None
            receive_entry: dict[str, Any] | None = None

            for entry in entries:
                amount = entry["amount"]
                asset = entry["asset"]
                entry_type = entry["type"]

                if (entry_type == "spend" or amount < 0) and asset in fiat_currencies:
                    if spend_entry is None or abs(amount) > abs(spend_entry["amount"]):
                        spend_entry = entry
                elif (entry_type == "receive" or amount > 0) and asset not in fiat_currencies:  # noqa: SIM102
                    if receive_entry is None or abs(amount) > abs(receive_entry["amount"]):
                        receive_entry = entry

            if spend_entry and receive_entry and spend_entry["asset"] in fiat_currencies:
                crypto_amount = abs(receive_entry["amount"])
                fiat_amount = abs(spend_entry["amount"])
                fiat_currency = spend_entry["asset"]

                if crypto_amount > 0:
                    price = fiat_amount / crypto_amount

                    fiat_fee = spend_entry["fee"]

                    trades.append(
                        ExchangeTrade(
                            trade_id=f"instant_{refid}",
                            symbol=f"{receive_entry['asset']}{fiat_currency}",
                            side="buy",
                            quantity=crypto_amount,
                            price=price,
                            fee=fiat_fee,
                            fee_currency=fiat_currency,
                            timestamp=receive_entry["time"],
                        )
                    )
                    processed_refids.add(refid)

        return sorted(trades, key=lambda x: x.timestamp, reverse=True), processed_refids
