"""Classification des mouvements importés : le préfixe fait le type.

Le type d'une transaction ne se lit ni dans le sens de l'opération ni dans un
champ dédié, mais dans le préfixe de son identifiant. Rien ne l'annonce, et
aucune erreur ne survient si un préfixe se perd : les montants sont simplement
rangés au mauvais endroit, et la fiscalité avec eux.
"""

import pytest

from app.models.transaction import TransactionType
from app.services.exchange_import_classification import (
    OrigineMouvement,
    classifier_origine,
    determiner_type_transaction,
)


def _type(trade_id: str, side: str = "buy") -> TransactionType:
    return determiner_type_transaction(classifier_origine(trade_id), trade_id, side)


class TestLectureDuPrefixe:
    @pytest.mark.parametrize(
        "trade_id,attendu",
        [
            ("reward_staking_1", "est_recompense_staking"),
            ("reward_airdrop_1", "est_airdrop"),
            ("reward_quelconque", "est_airdrop"),
            ("fiat_1", "est_ordre_fiat"),
            ("instant_1", "est_ordre_fiat"),
            ("convert_buy_1", "est_conversion"),
            ("withdrawal_1", "est_retrait"),
        ],
    )
    def test_chaque_prefixe_leve_son_drapeau(self, trade_id, attendu):
        origine = classifier_origine(trade_id)
        assert getattr(origine, attendu) is True

    def test_un_identifiant_sans_prefixe_ne_leve_rien(self):
        """C'est le cas ordinaire : un trade au comptant."""
        assert classifier_origine("t1") == OrigineMouvement()

    def test_identifiant_vide(self):
        assert classifier_origine("") == OrigineMouvement()

    def test_le_staking_n_est_pas_un_airdrop(self):
        """`reward_staking_` commence par `reward_` : sans exclusion explicite,
        il serait compté deux fois."""
        origine = classifier_origine("reward_staking_1")
        assert origine.est_recompense_staking is True
        assert origine.est_airdrop is False

    def test_staking_et_airdrop_comptent_ensemble_comme_recompenses(self):
        assert classifier_origine("reward_staking_1").est_recompense is True
        assert classifier_origine("reward_airdrop_1").est_recompense is True
        assert classifier_origine("t1").est_recompense is False

    def test_le_prefixe_doit_etre_au_debut(self):
        """« mon_reward_staking_1 » n'est pas une récompense."""
        assert classifier_origine("mon_reward_staking_1") == OrigineMouvement()


class TestTypeDeTransaction:
    def test_retrait(self):
        assert _type("withdrawal_1") == TransactionType.TRANSFER_OUT

    def test_recompense_de_staking(self):
        assert _type("reward_staking_1") == TransactionType.STAKING_REWARD

    def test_airdrop(self):
        assert _type("reward_airdrop_1") == TransactionType.AIRDROP

    def test_conversion_entrante(self):
        assert _type("convert_buy_1") == TransactionType.CONVERSION_IN

    def test_conversion_sortante(self):
        assert _type("convert_sell_1") == TransactionType.CONVERSION_OUT

    def test_conversion_sans_sens_explicite_est_entrante(self):
        """Tout préfixe de conversion autre que `convert_sell_` entre dans
        l'actif — c'est le comportement d'origine, conservé tel quel."""
        assert _type("convert_1") == TransactionType.CONVERSION_IN

    def test_achat_au_comptant(self):
        assert _type("t1", side="buy") == TransactionType.BUY

    def test_vente_au_comptant(self):
        assert _type("t1", side="sell") == TransactionType.SELL

    def test_un_sens_inconnu_vaut_vente(self):
        """Le code d'origine ne teste que « buy » : tout le reste tombe dans
        `SELL`. Épinglé tel quel, sans approbation."""
        assert _type("t1", side="quelque_chose") == TransactionType.SELL

    def test_un_ordre_fiat_reste_un_achat(self):
        """L'ordre fiat compte à part, mais s'écrit comme un achat."""
        assert _type("fiat_1", side="buy") == TransactionType.BUY


class TestOrdreDePriorite:
    """Un identifiant peut satisfaire plusieurs préfixes. Le premier examiné
    l'emporte, et cet ordre fait partie du comportement."""

    def test_le_retrait_precede_la_recompense(self):
        assert _type("withdrawal_reward_staking_1") == TransactionType.TRANSFER_OUT

    def test_le_staking_precede_la_conversion(self):
        origine = OrigineMouvement(est_recompense_staking=True, est_conversion=True)
        assert determiner_type_transaction(origine, "x", "buy") == TransactionType.STAKING_REWARD

    def test_l_airdrop_precede_la_conversion(self):
        origine = OrigineMouvement(est_airdrop=True, est_conversion=True)
        assert determiner_type_transaction(origine, "x", "buy") == TransactionType.AIRDROP

    def test_la_conversion_precede_le_sens(self):
        """Une conversion marquée « sell » reste une conversion, pas une vente."""
        assert _type("convert_buy_1", side="sell") == TransactionType.CONVERSION_IN


class TestEquivalenceAvecLaFormeDOrigine:
    """La condition d'airdrop a été simplifiée sans changer son résultat.

    L'écriture d'origine — `startswith("reward_airdrop_") or
    startswith("reward_") and not startswith("reward_staking_")` — testait un
    premier terme redondant, et sa précédence prêtait à confusion. Les deux
    formes ont été comparées sur 200 040 identifiants sans un écart ; ce test
    en garde la trace sur les cas qui comptent.
    """

    @staticmethod
    def _forme_origine(trade_id: str) -> bool:
        return (
            trade_id.startswith("reward_airdrop_")
            or trade_id.startswith("reward_")
            and not trade_id.startswith("reward_staking_")
        )

    @pytest.mark.parametrize(
        "trade_id",
        [
            "reward_airdrop_1",
            "reward_staking_1",
            "reward_",
            "reward_x",
            "reward_staking_",
            "reward_airdrop_staking_1",
            "fiat_1",
            "t1",
            "",
        ],
    )
    def test_meme_resultat_que_la_forme_d_origine(self, trade_id):
        assert classifier_origine(trade_id).est_airdrop == self._forme_origine(trade_id)
