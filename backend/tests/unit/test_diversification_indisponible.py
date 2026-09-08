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

from app.services.smart_insights_service import smart_insights_service as svc


def titres(insights):
    return [i.title for i in insights]


class TestDiversificationConnue:
    def test_un_portefeuille_disperse_est_felicite(self):
        insights = svc._analyze_diversification(hhi=0.05, top_holdings=[])

        assert titres(insights) == ["Bonne diversification"]

    def test_un_portefeuille_concentre_est_signale(self):
        insights = svc._analyze_diversification(hhi=0.50, top_holdings=[])

        assert titres(insights) == ["Portfolio peu diversifié"]


class TestDiversificationInconnue:
    def test_une_mesure_absente_ne_produit_aucun_verdict(self):
        """`hhi=None` signifie « on ne sait pas », et doit rester muet.

        Avant correction, l'échec était converti en `0.0`, que le seuil
        `hhi < 0.10` traduisait en « Bonne diversification » — la conclusion la
        plus rassurante possible, tirée d'une absence de donnée.
        """
        insights = svc._analyze_diversification(hhi=None, top_holdings=[])

        assert insights == []

    def test_les_lignes_lourdes_restent_signalees_sans_hhi(self):
        """Le poids de la première ligne est une mesure distincte du HHI.

        Il vient d'`allocation_by_asset`, pas de l'analyse de diversification :
        si l'une échoue et pas l'autre, l'alerte de concentration doit
        subsister.
        """
        insights = svc._analyze_diversification(hhi=None, top_holdings=[{"symbol": "BTC", "weight": 0.45}])

        assert titres(insights) == ["Concentration excessive"]

    def test_le_score_de_sante_ne_penalise_pas_une_mesure_absente(self):
        # On ne pénalise pas ce qu'on ignore — mais on ne félicite pas non plus,
        # ce que la correction assure côté insights.
        connu, _ = svc._calculate_overall_score(sharpe=1.0, volatility=0.1, var_95=0.0, hhi=0.0, anomaly_count=0)
        inconnu, _ = svc._calculate_overall_score(sharpe=1.0, volatility=0.1, var_95=0.0, hhi=None, anomaly_count=0)

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

    def test_l_echec_de_l_analyse_assigne_none_et_non_un_nombre(self):
        import ast
        from pathlib import Path

        import app.services.smart_insights_service as module

        arbre = ast.parse(Path(module.__file__).read_text())
        assignations = []
        for n in ast.walk(arbre):
            if not isinstance(n, ast.ExceptHandler):
                continue
            for c in ast.walk(n):
                if isinstance(c, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "hhi" for t in c.targets):
                    assignations.append(c.value)

        assert assignations, "le gestionnaire qui retombe sur `hhi` a disparu"
        for valeur in assignations:
            est_none = isinstance(valeur, ast.Constant) and valeur.value is None
            assert est_none, (
                "un échec d'analyse de diversification doit donner `hhi = None`, "
                "pas un nombre : un zéro passe le seuil de 0,10 et produit "
                "« Bonne diversification » sur une mesure inexistante."
            )
