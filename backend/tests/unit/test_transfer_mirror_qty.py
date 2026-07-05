"""Tests de la quantité nette d'un mirror TRANSFER_IN (cold wallet).

Verrouille le fix du double-décompte des frais réseau : les APIs d'exchange
(Binance/Kraken) rapportent un montant de retrait DÉJÀ net des frais — le
mirror ne doit pas les re-soustraire. Cas réel prod (2026-06-28, Binance →
Tangem) : SOL OUT 2.99926463 fee 0.001 → reçu on-chain 2.99926463 exactement.
"""

from decimal import Decimal

from app.services.transfer_service import mirror_received_qty

D = Decimal


class TestMirrorReceivedQty:
    def test_exchange_api_amount_is_net_no_double_deduction(self):
        # Binance SOL réel : amount déjà net, fee prélevée en plus
        assert mirror_received_qty(D("2.99926463"), D("0.001"), "SOL", "SOL", amount_is_net=True) == D("2.99926463")

    def test_manual_entry_gross_deducts_network_fee(self):
        # Saisie manuelle : montant envoyé brut, frais réseau dans l'asset
        assert mirror_received_qty(D("1.0"), D("0.0002"), "BTC", "BTC", amount_is_net=False) == D("0.9998")

    def test_manual_entry_fee_in_other_currency_not_deducted(self):
        # Frais en EUR (pas dans l'asset transféré) : rien à déduire du qty
        assert mirror_received_qty(D("1.0"), D("5"), "EUR", "BTC", amount_is_net=False) == D("1.0")

    def test_manual_entry_empty_fee_currency_assumed_same_asset(self):
        # Historique : fee_currency vide = frais dans l'asset transféré
        assert mirror_received_qty(D("1.0"), D("0.01"), "", "ETH", amount_is_net=False) == D("0.99")

    def test_zero_fee_identity(self):
        assert mirror_received_qty(D("3"), D("0"), "SOL", "SOL", amount_is_net=False) == D("3")
        assert mirror_received_qty(D("3"), D("0"), "SOL", "SOL", amount_is_net=True) == D("3")
