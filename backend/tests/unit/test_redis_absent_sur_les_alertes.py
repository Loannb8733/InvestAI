"""Une panne de Redis ne doit pas transformer une route en erreur 500.

Même famille que NEW-69, cherchée délibérément après lui : ce défaut-là avait
fait tomber l'écran d'accueil en production, et un balayage des accès Redis non
gardés a montré qu'il avait deux frères, tous deux sur un chemin de requête.

Ce qui distingue ces deux cas de NEW-69 : il n'y a rien à quoi se replier. La
question n'est donc pas « où trouver la donnée » mais **que signifie son
absence**, et la réponse diffère d'un cas à l'autre.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.regime_alert_service import regime_alert_service
from app.services.telegram_service import telegram_service


def _redis_en_panne(cible):
    return patch(cible, new=AsyncMock(side_effect=ConnectionError("Upstash injoignable")))


class TestMemoireDuRegime:
    """Sans mémoire du régime précédent, aucun changement ne peut être établi."""

    async def test_la_lecture_rend_none_au_lieu_de_lever(self):
        with _redis_en_panne("app.services.regime_alert_service._get_redis_txt"):
            assert await regime_alert_service._get_last_regime() is None

    async def test_l_ecriture_ne_leve_pas_non_plus(self):
        with _redis_en_panne("app.services.regime_alert_service._get_redis_txt"):
            assert await regime_alert_service._set_last_regime("bullish") is None

    async def test_aucune_alerte_n_est_emise_faute_de_memoire(self):
        """Le comportement d'ensemble, et le seul qui compte pour l'utilisateur.

        `None` est aussi ce que rend une première exécution : le service amorce
        et se tait. Annoncer une mutation qu'on n'a pas constatée serait pire
        que le silence — l'alerte de régime sert à signaler un basculement, pas
        à signaler qu'on a oublié le précédent.
        """
        with _redis_en_panne("app.services.regime_alert_service._get_redis_txt"), patch.object(
            regime_alert_service, "_get_current_regime", new=AsyncMock(return_value="bearish")
        ):
            resultat = await regime_alert_service.check_and_alert()

        assert resultat["status"] == "seed"


class TestPauseEntreDeuxAlertes:
    """Sans la pause, on préfère le doublon au silence."""

    async def test_le_message_part_quand_la_pause_est_illisible(self):
        """Deux imperfections, une seule acceptable.

        Un doublon se remarque et s'ignore ; un silence sur une alerte de prix
        ne se voit pas. La panne ne doit donc pas retenir le message.
        """
        with _redis_en_panne("app.services.telegram_service._get_redis"):
            assert await telegram_service._is_on_cooldown("alerte:BTC") is False

    async def test_poser_la_pause_ne_leve_pas(self):
        with _redis_en_panne("app.services.telegram_service._get_redis"):
            assert await telegram_service._set_cooldown("alerte:BTC") is None

    @pytest.mark.parametrize("presente,attendu", [(1, True), (0, False)])
    async def test_la_pause_reste_lue_quand_redis_repond(self, presente, attendu):
        """La garde ne doit pas court-circuiter le chemin normal.

        Les **deux** réponses comptent : une clé présente retient le message,
        une clé absente le laisse partir. N'éprouver que la première laisserait
        passer un `return True` constant — qui étoufferait toutes les alertes,
        exactement l'inverse du service rendu.
        """
        client = AsyncMock()
        client.exists = AsyncMock(return_value=presente)

        with patch("app.services.telegram_service._get_redis", new=AsyncMock(return_value=client)):
            assert await telegram_service._is_on_cooldown("alerte:BTC") is attendu
