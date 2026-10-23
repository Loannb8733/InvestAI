import logging
from datetime import datetime
from decimal import Decimal

from app.domains.exchanges.connectors.base import ExchangeDeposit, ExchangeWithdrawal
from app.domains.exchanges.connectors.bitstamp.core import BitstampCore

logger = logging.getLogger(__name__)


class BitstampMovements(BitstampCore):
    async def get_deposits(  # noqa: C901
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeDeposit]:
        """Dépôts extraits des user_transactions de type 0 ; la devise est le premier montant positif."""
        deposits: list[ExchangeDeposit] = []
        offset = 0
        page_size = 100

        try:
            while len(deposits) < limit:
                transactions = await self._get_user_transactions(offset=offset, limit=page_size)

                if not transactions:
                    break

                for tx in transactions:
                    if len(deposits) >= limit:
                        break

                    if int(tx.get("type", -1)) != 0:
                        continue

                    tx_datetime = datetime.fromisoformat(tx.get("datetime", "").replace(" ", "T"))

                    if start_time and tx_datetime < start_time:
                        continue

                    deposit_currency = None
                    deposit_amount = Decimal("0")

                    for key, value in tx.items():
                        if key in ("id", "type", "datetime", "fee", "order_id"):
                            continue
                        try:
                            amount = Decimal(str(value))
                            if amount > 0:
                                deposit_currency = key.upper()
                                deposit_amount = amount
                                break
                        except Exception:  # noqa: BLE001
                            continue

                    if not deposit_currency:
                        continue

                    if symbol and deposit_currency != symbol.upper():
                        continue

                    deposits.append(
                        ExchangeDeposit(
                            deposit_id=str(tx.get("id", "")),
                            symbol=deposit_currency,
                            amount=deposit_amount,
                            timestamp=tx_datetime,
                            status="completed",
                            tx_id=None,
                        )
                    )

                if len(transactions) < page_size:
                    break
                offset += page_size

        except Exception as e:  # noqa: BLE001
            logger.error(f"Bitstamp get_deposits error: {e}")

        return deposits

    async def get_withdrawals(  # noqa: C901
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExchangeWithdrawal]:
        """Retraits extraits des user_transactions de type 1 ; la devise est le premier montant négatif."""
        withdrawals: list[ExchangeWithdrawal] = []
        offset = 0
        page_size = 100

        try:
            while len(withdrawals) < limit:
                transactions = await self._get_user_transactions(offset=offset, limit=page_size)

                if not transactions:
                    break

                for tx in transactions:
                    if len(withdrawals) >= limit:
                        break

                    if int(tx.get("type", -1)) != 1:
                        continue

                    tx_datetime = datetime.fromisoformat(tx.get("datetime", "").replace(" ", "T"))

                    if start_time and tx_datetime < start_time:
                        continue

                    withdrawal_currency = None
                    withdrawal_amount = Decimal("0")

                    for key, value in tx.items():
                        if key in ("id", "type", "datetime", "fee", "order_id"):
                            continue
                        try:
                            amount = Decimal(str(value))
                            if amount < 0:
                                withdrawal_currency = key.upper()
                                withdrawal_amount = abs(amount)
                                break
                        except Exception:  # noqa: BLE001
                            continue

                    if not withdrawal_currency:
                        continue

                    if symbol and withdrawal_currency != symbol.upper():
                        continue

                    fee = Decimal(str(tx.get("fee", "0")))

                    withdrawals.append(
                        ExchangeWithdrawal(
                            withdrawal_id=str(tx.get("id", "")),
                            symbol=withdrawal_currency,
                            amount=withdrawal_amount,
                            fee=fee,
                            timestamp=tx_datetime,
                            status="completed",
                            tx_id=None,
                            address=None,
                        )
                    )

                if len(transactions) < page_size:
                    break
                offset += page_size

        except Exception as e:  # noqa: BLE001
            logger.error(f"Bitstamp get_withdrawals error: {e}")

        return withdrawals
