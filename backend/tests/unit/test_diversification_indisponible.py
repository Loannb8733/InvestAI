from types import SimpleNamespace

"""Ce que dit le diagnostic quand l'analyse de diversification échoue.

`_generate_portfolio_health` rattrape toute erreur de
`get_diversification_analysis` et retombe sur `hhi = 0.0`. Or les analyseurs
lisent ce zéro comme une mesure : `hhi < 0.10` produit l'insight **« Bonne
diversification »**.

Un échec devient donc une assurance. C'est le même motif que le repli des
alertes sur le prix de revient (NEW-35) : une valeur de secours indistinguable
d'un vrai résultat, que l'appelant évalue comme tel.

Le score de santé s'en ressent aussi — un HHI nul n'entraîne aucune pénalité de
concentration, alors qu'on ne sait rien de la concentration réelle.
"""

from app.domains.analytics.service import analytics_service
from app.domains.insights.health import _concentration
from app.domains.insights.rules.diversification import diversification_insights
from app.domains.insights.score import overall_score


def titres(insights):
    return [i.title for i in insights]


class TestDiversificationConnue:
    def test_un_portefeuille_disperse_est_felicite(self):
        insights = diversification_insights(hhi=0.05, top_holdings=[])

        assert titres(insights) == ["Bonne diversification"]

    def test_un_portefeuille_concentre_est_signale(self):
        insights = diversification_insights(hhi=0.50, top_holdings=[])

        assert titres(insights) == ["Portfolio peu diversifié"]


class TestDiversificationInconnue:
    def test_une_mesure_absente_ne_produit_aucun_verdict(self):
        """`hhi=None` signifie « on ne sait pas », et doit rester muet.

        Avant correction, l'échec était converti en `0.0`, que le seuil
        `hhi < 0.10` traduisait en « Bonne diversification » — la conclusion la
        plus rassurante possible, tirée d'une absence de donnée.
        """
        insights = diversification_insights(hhi=None, top_holdings=[])

        assert insights == []

    def test_les_lignes_lourdes_restent_signalees_sans_hhi(self):
        """Le poids de la première ligne est une mesure distincte du HHI.

        Il vient d'`allocation_by_asset`, pas de l'analyse de diversification :
        si l'une échoue et pas l'autre, l'alerte de concentration doit
        subsister.
        """
        insights = diversification_insights(hhi=None, top_holdings=[{"symbol": "BTC", "weight": 0.45}])

        assert titres(insights) == ["Concentration excessive"]

    def test_le_score_de_sante_ne_penalise_pas_une_mesure_absente(self):
        # On ne pénalise pas ce qu'on ignore — mais on ne félicite pas non plus,
        # ce que la correction assure côté insights.
        connu, _ = overall_score(sharpe=1.0, volatility=0.1, var_95=0.0, hhi=0.0, anomaly_count=0)
        inconnu, _ = overall_score(sharpe=1.0, volatility=0.1, var_95=0.0, hhi=None, anomaly_count=0)

        assert connu == inconnu


class TestLaSourceDeclareSonEchec:
    """Garde statique sur le gestionnaire qui produit la mesure.

    Les tests ci-dessus appellent les analyseurs directement : ils ne
    traversent jamais le `except` de `_generate_portfolio_health`, si bien que
    l'y voir réassigner `0.0` ne les ferait pas tomber. C'est exactement le
    raccord non couvert qui a produit NEW-32.

    Monter le flux complet demanderait toute la chaîne analytics ; la
    régression à verrouiller est déclarative — un échec ne doit pas ressortir
    en nombre. Le projet emploie déjà ce genre de garde
    (`test_pas_de_boucle_fermee`, `test_pas_de_commit_sans_rollback`).
    """

    async def test_l_echec_de_l_analyse_rend_none_et_non_un_nombre(self, monkeypatch):
        async def echec(*_args, **_kwargs):
            raise RuntimeError("analyse indisponible")

        monkeypatch.setattr(analytics_service, "get_diversification_analysis", echec)

        hhi, lignes = await _concentration(None, "utilisateur", SimpleNamespace(allocation_by_asset={"BTC": 100.0}))

        assert hhi is None
        assert lignes == []
