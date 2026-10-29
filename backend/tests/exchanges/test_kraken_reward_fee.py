from datetime import UTC, datetime
from decimal import Decimal

from app.domains.exchanges.connectors.kraken.connector import KrakenService

D = Decimal


async def test_a_staking_reward_is_credited_net_of_the_kraken_commission() -> None:
    kraken = KrakenService(api_key="cle-de-test", secret_key="c2VjcmV0")
    entry = {
        "ledger_id": "L1",
        "refid": "R1",
        "time": datetime(2026, 10, 18, 14, 28, tzinfo=UTC),
        "type": "staking",
        "subtype": "",
        "asset": "SOL",
        "amount": D("0.0009366349"),
        "fee": D("0.0002341587"),
    }
    [reward] = await kraken.get_rewards(ledgers=[entry])
    assert (reward.quantity, reward.fee, reward.fee_currency) == (D("0.0007024762"), D("0.0002341587"), "SOL")
