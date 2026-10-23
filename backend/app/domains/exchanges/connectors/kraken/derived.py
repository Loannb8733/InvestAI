import logging
from decimal import Decimal
from typing import Any

from app.domains.exchanges.connectors.base import ExchangeTrade
from app.domains.exchanges.connectors.kraken.ledgers import KrakenLedgers

logger = logging.getLogger(__name__)


class KrakenDerived(KrakenLedgers):
    async def get_crypto_conversions(  # noqa: C901
        self, limit: int = 500, exclude_refids: set[str] | None = None, ledgers: list[dict[str, Any]] | None = None
    ) -> list[ExchangeTrade]:
        """Conversions crypto contre crypto du grand livre, chacune en deux trades à prix nul.

        Les refid de exclude_refids, déjà retenus comme achats instantanés, sont ignorés.
        """
        trades: list[ExchangeTrade] = []
        if exclude_refids is None:
            exclude_refids = set()

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
            if refid in processed_refids or refid in exclude_refids:
                continue

            sell_entry: dict[str, Any] | None = None
            buy_entry: dict[str, Any] | None = None

            for entry in entries:
                amount = entry["amount"]
                asset = entry["asset"]

                if asset in fiat_currencies:
                    continue

                if amount < 0:
                    sell_entry = entry
                elif amount > 0:
                    buy_entry = entry

            if sell_entry and buy_entry:
                sell_amount = abs(sell_entry["amount"])
                buy_amount = abs(buy_entry["amount"])
                sell_asset = sell_entry["asset"]
                buy_asset = buy_entry["asset"]

                conversion_ratio = sell_amount / buy_amount if buy_amount > 0 else Decimal("0")

                trades.append(
                    ExchangeTrade(
                        trade_id=f"convert_sell_{refid}",
                        symbol=f"{sell_asset}EUR",
                        side="sell",
                        quantity=sell_amount,
                        price=Decimal("0"),
                        fee=sell_entry["fee"],
                        fee_currency=sell_asset,
                        timestamp=sell_entry["time"],
                    )
                )

                trades.append(
                    ExchangeTrade(
                        trade_id=f"convert_buy_{refid}",
                        symbol=f"{buy_asset}EUR",
                        side="buy",
                        quantity=buy_amount,
                        price=Decimal("0"),
                        fee=buy_entry["fee"],
                        fee_currency=buy_asset,
                        timestamp=buy_entry["time"],
                    )
                )

                processed_refids.add(refid)
                logger.debug(
                    f"Kraken: Found conversion {sell_asset} -> {buy_asset} (ratio: {float(conversion_ratio):.8f})"
                )

        logger.info(f"Kraken: Total crypto conversions found: {len(trades) // 2}")
        return sorted(trades, key=lambda x: x.timestamp, reverse=True)

    async def get_rewards(self, limit: int = 500, ledgers: list[dict[str, Any]] | None = None) -> list[ExchangeTrade]:
        """Récompenses positives du grand livre (staking, earn, airdrop, bonus...), en achats à prix nul."""
        trades: list[ExchangeTrade] = []

        if ledgers is None:
            ledgers = await self.get_ledgers(limit=limit)

        reward_types = ["reward", "staking", "credit", "airdrop", "bonus", "earn"]

        for entry in ledgers:
            entry_type = entry["type"]
            subtype = entry.get("subtype", "").lower()
            amount = entry["amount"]
            asset = entry["asset"]

            if asset in ["EUR", "USD", "GBP", "CAD", "JPY"]:
                continue

            is_reward = entry_type in reward_types or subtype in reward_types
            if is_reward and amount > 0:
                is_airdrop = entry_type in ("airdrop", "bonus") or subtype in (
                    "airdrop",
                    "bonus",
                )
                reward_prefix = "reward_airdrop_" if is_airdrop else "reward_staking_"

                trades.append(
                    ExchangeTrade(
                        trade_id=f"{reward_prefix}{entry['ledger_id']}",
                        symbol=f"{asset}EUR",
                        side="buy",
                        quantity=amount,
                        price=Decimal("0"),
                        fee=entry["fee"],
                        fee_currency="EUR",
                        timestamp=entry["time"],
                    )
                )
                logger.debug(f"Kraken reward: {entry_type}/{subtype} - {amount} {asset}")

        return sorted(trades, key=lambda x: x.timestamp, reverse=True)
