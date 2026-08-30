"""Réconciliation des entrées manquantes : quelles lignes écrire, et lesquelles jamais.

L'historique d'un actif peut sous-estimer la position réelle : la sync ne remonte
qu'une fenêtre limitée de l'exchange, alors que `asset.quantity` reflète le solde
renvoyé par l'API. La somme signée peut même devenir négative — impossible pour un
stock, donc preuve d'incomplétude.

Ces tests pinnent les garde-fous : on ne comble QUE les entrées manquantes, jamais
les sorties (leur nature — cession ou transfert — change le P&L réalisé et n'est pas
déductible du code), et jamais à coût nul (cela créerait une couche à coût zéro qui
surévalue la plus-value latente, cf. FIN-03).

Fonctions pures : ni DB, ni HTTP, ni Docker.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.transaction import TransactionType
from scripts.reconcile_missing_entries import history_net, missing_entry

D = Decimal


def tx(kind, qty):
    return SimpleNamespace(transaction_type=kind, quantity=qty)


class TestHistoryNet:
    def test_entrees_et_sorties(self):
        txs = [tx(TransactionType.BUY, 10), tx(TransactionType.SELL, 3)]
        assert history_net(txs) == D("7")

    def test_tous_les_types_entrants(self):
        txs = [
            tx(TransactionType.BUY, 1),
            tx(TransactionType.CONVERSION_IN, 1),
            tx(TransactionType.TRANSFER_IN, 1),
            tx(TransactionType.AIRDROP, 1),
            tx(TransactionType.STAKING_REWARD, 1),
            tx(TransactionType.DIVIDEND, 1),
            tx(TransactionType.INTEREST, 1),
        ]
        assert history_net(txs) == D("7")

    def test_staking_est_un_marqueur_pas_un_flux(self):
        # STAKING/UNSTAKING décrivent un état de position, pas un mouvement de stock.
        txs = [tx(TransactionType.BUY, 10), tx(TransactionType.STAKING, 5)]
        assert history_net(txs) == D("10")

    def test_historique_negatif_possible(self):
        # Signature d'un historique incomplet : plus de sorties que d'entrées connues.
        assert history_net([tx(TransactionType.SELL, 26)]) == D("-26")

    def test_quantite_nulle_ou_absente(self):
        assert history_net([tx(TransactionType.BUY, None)]) == D("0")


class TestEcrit:
    def test_entree_manquante_est_comblee(self):
        qty, _ = missing_entry(stored=D("1.05798199"), history=D("0.679352"), pru=D("71.16"))
        assert qty == D("0.37862999")

    def test_historique_negatif_est_ramene_au_solde(self):
        qty, _ = missing_entry(stored=D("0.00000098"), history=D("-26.54599355"), pru=D("0.93"))
        assert qty == D("26.54599453")


class TestNeTouchePas:
    def test_sortie_manquante_hors_perimetre(self):
        # Cold wallet : l'historique dépasse le solde. Nature indéterminable ici.
        qty, raison = missing_entry(stored=D("0"), history=D("109529"), pru=D("0.01"))
        assert qty is None
        assert "hors périmètre" in raison

    def test_pru_nul_refuse(self):
        qty, raison = missing_entry(stored=D("10"), history=D("0"), pru=D("0"))
        assert qty is None
        assert "coût zéro" in raison

    @pytest.mark.parametrize("gap", ["0", "0.0000001", "0.000001"])
    def test_poussiere_ignoree(self, gap):
        qty, _ = missing_entry(stored=D(gap), history=D("0"), pru=D("100"))
        assert qty is None

    def test_historique_deja_coherent(self):
        qty, _ = missing_entry(stored=D("5"), history=D("5"), pru=D("100"))
        assert qty is None

    def test_idempotence(self):
        # Après écriture, l'historique rejoint le solde : plus rien à proposer.
        stored, history, pru = D("1.05798199"), D("0.679352"), D("71.16")
        qty, _ = missing_entry(stored, history, pru)
        assert qty is not None
        qty2, _ = missing_entry(stored, history + qty, pru)
        assert qty2 is None
