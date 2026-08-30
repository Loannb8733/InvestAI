"""Extinction des positions Earn refermées.

Une position Earn n'est pas un flux mais un état : la sync la matérialise par une
transaction STAKING dont elle met la quantité à jour. Mais la boucle de sync n'itère
que sur les positions *encore ouvertes* — un actif retiré de l'Earn en sort, plus rien
ne le met à jour, et son marqueur restait figé indéfiniment. Le dashboard, qui valorise
STAKING - UNSTAKING, affichait donc une position inexistante (mesuré sur des données
réelles : 404 € de USDC affichés alors que le solde Binance était à zéro).

Ces tests pinnent la décision « quels marqueurs éteindre ». Fonction pure : ni DB,
ni HTTP, ni Docker.
"""

import pytest

from app.api.v1.endpoints.api_keys import earn_positions_to_close


class TestPositionRefermee:
    def test_un_marqueur_sans_position_est_eteint(self):
        rows = [("id-1", "USDC", 468.83607272)]
        assert earn_positions_to_close(rows, still_staked=set()) == [("id-1", "USDC", 468.83607272)]

    def test_seuls_les_absents_sont_eteints(self):
        rows = [("id-1", "USDC", 468.8), ("id-2", "ETH", 1.5)]
        closed = earn_positions_to_close(rows, still_staked={"ETH"})
        assert [c[1] for c in closed] == ["USDC"]

    def test_comparaison_insensible_a_la_casse(self):
        rows = [("id-1", "usdc", 100.0)]
        assert earn_positions_to_close(rows, still_staked={"USDC"}) == []
        assert earn_positions_to_close(rows, still_staked={"usdc"}) == []


class TestNeTouchePasAuReste:
    def test_position_toujours_ouverte_intacte(self):
        rows = [("id-1", "USDC", 468.8)]
        assert earn_positions_to_close(rows, still_staked={"USDC"}) == []

    def test_position_deja_soldee_ignoree(self):
        # STAKING 100 - UNSTAKING 100 = 0 : rien à éteindre, pas de double UNSTAKING.
        rows = [("id-1", "USDC", 0.0)]
        assert earn_positions_to_close(rows, still_staked=set()) == []

    def test_net_negatif_ignore(self):
        rows = [("id-1", "USDC", -5.0)]
        assert earn_positions_to_close(rows, still_staked=set()) == []

    @pytest.mark.parametrize("poussiere", [0.0, 0.00001, 0.0001])
    def test_poussiere_ignoree(self, poussiere):
        rows = [("id-1", "USDC", poussiere)]
        assert earn_positions_to_close(rows, still_staked=set()) == []

    def test_juste_au_dessus_du_seuil_est_eteint(self):
        rows = [("id-1", "USDC", 0.001)]
        assert len(earn_positions_to_close(rows, still_staked=set())) == 1


class TestRobustesse:
    def test_net_none_ne_leve_pas(self):
        assert earn_positions_to_close([("id-1", "USDC", None)], still_staked=set()) == []

    def test_aucune_ligne(self):
        assert earn_positions_to_close([], still_staked={"USDC"}) == []

    def test_idempotence(self):
        # Une fois l'UNSTAKING écrit, le net retombe à 0 : le second passage ne
        # doit plus rien proposer, sinon la sync empilerait des UNSTAKING.
        rows = [("id-1", "USDC", 468.8)]
        assert len(earn_positions_to_close(rows, set())) == 1
        assert earn_positions_to_close([("id-1", "USDC", 0.0)], set()) == []
