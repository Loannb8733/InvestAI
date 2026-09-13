"""Un cours indisponible ne doit pas devenir un prix de revient nul.

`_get_current_price` rendait **zéro** quand le fournisseur de prix ne répondait
pas. Or ce prix sert de prix de revient aux transferts entrants que crée la
synchronisation : ajustements de balance, dépôts externes, import d'un actif
nouveau. Une panne passagère transformait une vraie position en quantité
gratuite — prix de revient nul, plus-value fictive de 100 %.

Mesuré sur les données réelles le 2026-09-13 : 15 des 152 ajustements de balance
portaient un prix nul, sur de l'ETH et du SOL, qui ont toujours un cours. Une
fois sur dix. L'enjeu était de 0,13 € — des micro-corrections d'arrondi —, mais
le même zéro alimente les dépôts et les actifs nouveaux, où il porterait sur de
vraies positions.

Même famille que NEW-35 : un repli présenté comme une vraie valeur.
"""

import ast
import inspect
import logging
from unittest.mock import AsyncMock, patch

import pytest

from app.tasks import sync_exchanges
from app.tasks.sync_exchanges import _get_current_price


def _service_qui(**comportement):
    service = AsyncMock()
    service.get_price = AsyncMock(**comportement)
    return patch.object(sync_exchanges, "_price_service", service)


class TestCoursDisponible:
    async def test_le_cours_en_direct_est_retenu(self):
        with _service_qui(return_value={"price": 2145.81}):
            assert await _get_current_price("ETH", repli=2000.0) == pytest.approx(2145.81)

    async def test_le_repli_n_est_pas_utilise_quand_le_cours_repond(self, caplog):
        # Sans ce test, un correctif maladroit pourrait préférer le dernier
        # cours connu au cours en direct.
        with _service_qui(return_value={"price": 87.93}), caplog.at_level(logging.WARNING):
            await _get_current_price("SOL", repli=80.0)

        assert "indisponible" not in caplog.text


class TestCoursIndisponible:
    async def test_une_panne_retient_le_dernier_cours_connu(self):
        """Le cas mesuré : ETH et SOL ont un cours, le fournisseur était muet.

        Le dernier cours connu est une estimation — mais une estimation proche,
        là où zéro faisait de la position une quantité gratuite.
        """
        with _service_qui(side_effect=TimeoutError("fournisseur muet")):
            assert await _get_current_price("ETH", repli=2145.81) == pytest.approx(2145.81)

    async def test_une_reponse_sans_cours_retient_aussi_le_repli(self):
        # Le fournisseur répond, mais sans prix : même situation pour
        # l'appelant, qui était jusqu'ici traitée en silence.
        with _service_qui(return_value={"price": None}):
            assert await _get_current_price("ETH", repli=2145.81) == pytest.approx(2145.81)

    async def test_sans_cours_connu_le_prix_reste_nul(self):
        """Un jeton qui n'a jamais eu de cours : zéro dit alors la vérité.

        C'est aussi pourquoi l'écriture n'est pas sautée : pour un tel jeton, un
        « réessayer au passage suivant » ne convergerait jamais.
        """
        with _service_qui(side_effect=TimeoutError("fournisseur muet")):
            assert await _get_current_price("JETONOBSCUR") == 0.0

    @pytest.mark.parametrize("repli,attendu", [(2145.81, "dernier cours connu"), (0.0, "prix nul")])
    async def test_le_repli_se_voit_dans_le_journal(self, caplog, repli, attendu):
        # L'ancienne version ne disait rien quand le fournisseur répondait sans
        # prix : le zéro s'inscrivait sans trace.
        with _service_qui(return_value={}), caplog.at_level(logging.WARNING, logger="app.tasks.sync_exchanges"):
            await _get_current_price("ETH", repli=repli)

        assert attendu in caplog.text


class TestAppelants:
    """Là où un actif existe, son dernier cours doit être transmis.

    La fonction ne sert à rien si les appelants ne passent pas le repli :
    `_sync_detailed_transactions` fait six cents lignes, et ce contrôle de forme
    est le moyen le plus sûr de vérifier les sites d'appel.
    """

    def _appels(self):
        arbre = ast.parse(inspect.getsource(sync_exchanges))
        return [
            n
            for n in ast.walk(arbre)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_get_current_price"
        ]

    def test_les_depots_et_ajustements_transmettent_le_dernier_cours(self):
        avec_repli = [a for a in self._appels() if any(k.arg == "repli" for k in a.keywords)]

        assert len(avec_repli) == 2, "dépôts externes et ajustements de balance doivent passer le dernier cours connu"

    def test_seul_l_import_d_un_actif_nouveau_s_en_passe(self):
        # Un actif qui n'existe pas encore n'a pas de dernier cours : c'est le
        # seul site légitime sans repli.
        assert len(self._appels()) == 3
