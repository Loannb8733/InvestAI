"""Unit tests for CUMP PRU transfer handling (FIN-03 / audit F-06).

Pins the unified rule: a zero-price TRANSFER_IN of an already-held coin is an
internal wallet move and must inherit the running average cost (PRU stays stable),
NOT dilute it toward zero. Mirrors the FIFO engine's unmatched-transfer recovery.
"""

from decimal import Decimal

from app.models.transaction import TransactionType
from app.services.metrics_service import compute_cump_pru


class _Tx:
    def __init__(self, ttype, qty, price, *, fee=0, asset_id="a1"):
        self.transaction_type = ttype
        self.quantity = Decimal(str(qty))
        self.price = Decimal(str(price))
        self.fee = Decimal(str(fee))
        self.asset_id = asset_id


_AID = {"a1": "BTC"}
_EXCH = {"a1": "binance"}


def test_zero_price_transfer_in_keeps_pru_stable():
    txs = [
        _Tx(TransactionType.BUY, qty=1, price=100),
        _Tx(TransactionType.TRANSFER_IN, qty=1, price=0),  # internal move, no price
    ]
    pru = compute_cump_pru(txs, _AID, _EXCH)
    # PRU must remain 100, not be diluted to 50 by the cost-free unit.
    assert pru[("BTC", "binance")] == Decimal("100")


def test_priced_transfer_in_still_blends_cost():
    txs = [
        _Tx(TransactionType.BUY, qty=1, price=100),
        _Tx(TransactionType.TRANSFER_IN, qty=1, price=200),  # real recorded cost
    ]
    pru = compute_cump_pru(txs, _AID, _EXCH)
    # (100 + 200) / 2 = 150
    assert pru[("BTC", "binance")] == Decimal("150")


def test_zero_price_transfer_in_with_no_prior_holding_has_no_pru():
    # No prior cost to inherit -> remains cost-free, no PRU surfaced.
    txs = [_Tx(TransactionType.TRANSFER_IN, qty=1, price=0)]
    pru = compute_cump_pru(txs, _AID, _EXCH)
    assert ("BTC", "binance") not in pru
