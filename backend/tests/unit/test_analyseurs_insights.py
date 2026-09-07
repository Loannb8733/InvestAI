"""Filet de caractérisation des analyseurs d'insights et du score de santé.

`smart_insights_analyzers.py` — les règles qui produisent les conseils affichés
à l'utilisateur — est couvert à **8 %**, et `_calculate_overall_score`, la note
de 0 à 100 du portefeuille, ne l'est guère mieux. Ce sont des fonctions pures :
elles prennent des scalaires et rendent des recommandations.

Ce que ces tests tiennent avant tout, c'est le **contrat d'unité**. Volatilité,
VaR, drawdown, HHI et poids de ligne circulent tous en *fraction* (0,35 = 35 %)
alors que les services qui les calculent les rendent en *pourcentage*. La
conversion vit dans l'appelant, adossée à un commentaire. Sans test, retirer une
division par 100 ferait basculer tout portefeuille en « volatilité extrême »
sans qu'aucune suite ne bronche.

Comportement actuel épinglé, pas spécification approuvée.
"""

from app.ml import adaptive_thresholds as adaptive_th
from app.services.smart_insights_service import smart_insights_service as svc
from app.services.smart_insights_types import InsightSeverity


def titres(insights):
    return [i.title for i in insights]


def severites(insights):
    return [i.severity for i in insights]


class TestSeuilsDeReference:
    """Les seuils sont des constantes de convention, non dépendantes des données.

    Les tests qui suivent s'appuient sur ces valeurs ; les figer ici rend
    lisible ce qui casserait si elles bougeaient.
    """

    def test_les_seuils_sont_deterministes_sans_contexte_de_marche(self):
        assert adaptive_th.sharpe_classification() == (1.5, 1.0, 0.5, 0.0)
        assert adaptive_th.volatility_warning_thresholds() == (50.0, 80.0)
        assert adaptive_th.var_warning_thresholds() == (0.10, 0.15)
        assert adaptive_th.concentration_thresholds() == (0.25, 0.40)


class TestAnalyseDuSharpe:
    def test_un_sharpe_negatif_est_critique(self):
        insights = svc._analyze_sharpe(-0.5, 0.0)

        assert titres(insights) == ["Performance très faible"]
        assert severites(insights) == [InsightSeverity.CRITICAL]

    def test_un_sharpe_sous_le_seuil_correct_est_un_avertissement(self):
        assert titres(svc._analyze_sharpe(0.3, 0.0)) == ["Performance à améliorer"]

    def test_un_sharpe_entre_correct_et_bon_est_informatif(self):
        assert titres(svc._analyze_sharpe(0.8, 0.0)) == ["Performance correcte"]

    def test_un_sharpe_au_dessus_du_bon_seuil_est_excellent(self):
        # Le libellé bascule à `>= 1.0`, pas à 1,5 : « excellent » couvre donc
        # aussi ce que la classification appelle « bon ».
        assert titres(svc._analyze_sharpe(1.0, 0.0)) == ["Excellente performance"]
        assert titres(svc._analyze_sharpe(2.5, 0.0)) == ["Excellente performance"]

    def test_un_sharpe_exactement_nul_n_est_pas_critique(self):
        # Le test est `< 0.0`, strict : un Sharpe nul tombe dans la branche
        # suivante, « à améliorer ».
        assert titres(svc._analyze_sharpe(0.0, 0.0)) == ["Performance à améliorer"]


class TestAnalyseDuRisque:
    def test_la_volatilite_est_lue_en_fraction_et_non_en_pourcentage(self):
        """Le seuil « extrême » est de 80 %, soit 0,80 en fraction.

        Passer 80 au lieu de 0,80 — la valeur que rend `calculate_volatility` —
        déclencherait l'alerte extrême sur n'importe quel portefeuille. C'est
        exactement ce que la division par 100 de l'appelant empêche.
        """
        calme = svc._analyze_risk(volatility=0.30, var_95=0.0, max_drawdown=0.0)
        extreme = svc._analyze_risk(volatility=0.85, var_95=0.0, max_drawdown=0.0)
        mal_convertie = svc._analyze_risk(volatility=30.0, var_95=0.0, max_drawdown=0.0)

        assert titres(calme) == []
        assert titres(extreme) == ["Volatilité extrême"]
        assert titres(mal_convertie) == ["Volatilité extrême"]

    def test_une_volatilite_elevee_sans_etre_extreme_avertit(self):
        assert titres(svc._analyze_risk(0.60, 0.0, 0.0)) == ["Volatilité élevée"]

    def test_la_var_declenche_a_dix_puis_quinze_pour_cent(self):
        assert titres(svc._analyze_risk(0.0, 0.12, 0.0)) == ["VaR à surveiller"]
        assert titres(svc._analyze_risk(0.0, 0.20, 0.0)) == ["Risque de perte élevé"]

    def test_le_drawdown_declenche_a_quinze_puis_vingt_cinq_pour_cent(self):
        assert titres(svc._analyze_risk(0.0, 0.0, 0.18)) == ["Drawdown important"]
        assert titres(svc._analyze_risk(0.0, 0.0, 0.30)) == ["Drawdown severe"]

    def test_les_trois_metriques_s_accumulent(self):
        # Un portefeuille en mauvaise posture reçoit les trois alertes, pas la
        # plus grave seulement.
        insights = svc._analyze_risk(volatility=0.85, var_95=0.20, max_drawdown=0.30)

        assert len(insights) == 3


class TestAnalyseDeLaDiversification:
    def test_le_poids_de_la_premiere_ligne_est_lu_en_fraction(self):
        # 0,45 = 45 % du portefeuille. L'appelant divise par 100 les poids que
        # lui donne `allocation_by_asset`, exprimés en pourcentages.
        lourd = svc._analyze_diversification(hhi=0.15, top_holdings=[{"symbol": "BTC", "weight": 0.45}])

        assert titres(lourd) == ["Concentration excessive"]

    def test_entre_vingt_cinq_et_quarante_pour_cent_l_alerte_est_moderee(self):
        insights = svc._analyze_diversification(0.15, [{"symbol": "BTC", "weight": 0.30}])

        assert titres(insights) == ["Concentration élevée"]
        assert severites(insights) == [InsightSeverity.WARNING]

    def test_le_hhi_est_attendu_en_fraction_zero_un(self):
        """`_analyze_diversification` compare le HHI à 0,25 et 0,10.

        Deux HHI coexistent dans le projet, à des échelles différentes :
        `analytics_scoring._hhi` rend une **fraction** (somme des carrés des
        parts, 1,0 pour un mono-actif) et c'est celui qui arrive ici, tandis que
        `snapshot_risk.calculate_hhi` rend l'échelle **0-10000** de la
        convention antitrust. Les intervertir ferait déclarer « concentration
        élevée » à tout portefeuille, y compris parfaitement diversifié.
        """
        concentre = svc._analyze_diversification(hhi=0.50, top_holdings=[])
        diversifie = svc._analyze_diversification(hhi=0.05, top_holdings=[])

        assert titres(concentre) == ["Portfolio peu diversifié"]
        assert titres(diversifie) == ["Bonne diversification"]

    def test_un_hhi_intermediaire_ne_dit_rien(self):
        # Entre 0,10 et 0,25 : ni alerte, ni félicitation.
        assert svc._analyze_diversification(hhi=0.18, top_holdings=[]) == []

    def test_sans_ligne_ni_hhi_aucun_insight(self):
        assert svc._analyze_diversification(hhi=0.15, top_holdings=[]) == []


class TestScoreDeSante:
    def base(self, **surcharges):
        params = {
            "sharpe": 2.0,
            "volatility": 0.10,
            "var_95": 0.0,
            "hhi": 0.0,
            "anomaly_count": 0,
            "max_drawdown": 0.0,
        }
        params.update(surcharges)
        return svc._calculate_overall_score(**params)

    def test_un_portefeuille_ideal_depasse_cent_et_se_fait_brider(self):
        # 100 de base + 10 de bonus Sharpe = 110, ramené à 100.
        score, statut = self.base()

        assert score == 100
        assert statut == "excellent"

    def test_un_sharpe_negatif_coute_trente_points(self):
        score, _ = self.base(sharpe=-0.5)

        assert score == 70

    def test_les_penalites_se_cumulent(self):
        # Sharpe négatif (-30), volatilité extrême (-20), VaR critique (-15),
        # concentration critique (-15), drawdown > 40 % (-35) : le total
        # dépasse 100 et le score est bridé à 0, pas négatif.
        score, statut = self.base(sharpe=-1.0, volatility=0.90, var_95=0.20, hhi=0.50, max_drawdown=0.50)

        assert score == 0
        assert statut != "excellent"

    def test_les_anomalies_coutent_cinq_points_chacune_plafonnees_a_vingt(self):
        assert self.base(anomaly_count=2)[0] == 100 - 10 + 10
        assert self.base(anomaly_count=10)[0] == self.base(anomaly_count=4)[0]

    def test_le_drawdown_est_lu_en_valeur_absolue(self):
        # Un drawdown de -30 % et de +30 % pénalisent identiquement : le signe
        # varie selon la source.
        assert self.base(max_drawdown=-0.30) == self.base(max_drawdown=0.30)

    def test_une_correlation_elevee_entre_les_cinq_premieres_lignes_penalise(self):
        # Diversification illusoire : cinq lignes qui montent et descendent
        # ensemble ne diversifient rien.
        # Sharpe volontairement moyen : avec un Sharpe excellent, le bonus
        # +10 pousse le total au-delà de 100 et le bridage masque la pénalité.
        sans = self.base(sharpe=0.8, avg_top5_corr=0.0)[0]
        avec = self.base(sharpe=0.8, avg_top5_corr=0.90)[0]

        assert sans - avec == 15

    def test_les_paliers_de_statut(self):
        # 80 et plus « excellent », 65 « good », 50 « fair ». Les scores sont
        # atteints en dosant la pénalité de drawdown depuis 110 bridé à 100.
        assert self.base()[1] == "excellent"
        assert self.base(sharpe=0.8, max_drawdown=0.30)[1] == "good"
        assert self.base(sharpe=-1.0, max_drawdown=0.20)[1] == "fair"


class TestAnalyseDesCorrelations:
    """Corrélations : diversification illusoire et clusters de risque.

    `corr_data` est un objet portant `symbols`, `matrix` et
    `strongly_correlated` — un triplet `(s1, s2, corr)` par paire notable. Un
    `SimpleNamespace` suffit : la fonction ne lit rien d'autre.
    """

    def donnees(self, symboles, matrice, fortes=()):
        from types import SimpleNamespace

        return SimpleNamespace(symbols=symboles, matrix=matrice, strongly_correlated=list(fortes))

    def lignes(self, *symboles):
        return [{"symbol": s, "weight": 0.2} for s in symboles]

    def test_moins_de_deux_actifs_ne_dit_rien(self):
        insights, moyenne, clusters = svc._analyze_correlation(self.donnees(["BTC"], [[1.0]]), self.lignes("BTC"))

        assert (insights, moyenne, clusters) == ([], 0.0, [])

    def test_la_moyenne_ne_porte_que_sur_les_cinq_premieres_lignes(self):
        """Un sixième actif fortement corrélé n'entre pas dans la moyenne.

        La matrice couvre trois actifs, mais seuls BTC et ETH figurent au
        classement : seule leur paire compte, et la corrélation de 0,1 du
        troisième est ignorée.
        """
        corr = self.donnees(
            ["BTC", "ETH", "GOLD"],
            [[1.0, 0.9, 0.1], [0.9, 1.0, 0.1], [0.1, 0.1, 1.0]],
        )

        _, moyenne, _ = svc._analyze_correlation(corr, self.lignes("BTC", "ETH"))

        assert moyenne == 0.9

    def test_une_correlation_moyenne_elevee_signale_une_diversification_illusoire(self):
        corr = self.donnees(["BTC", "ETH"], [[1.0, 0.75], [0.75, 1.0]])

        insights, _, _ = svc._analyze_correlation(corr, self.lignes("BTC", "ETH"))

        assert titres(insights) == ["Diversification illusoire"]
        assert severites(insights) == [InsightSeverity.WARNING]

    def test_au_dela_de_085_l_alerte_devient_critique(self):
        corr = self.donnees(["BTC", "ETH"], [[1.0, 0.95], [0.95, 1.0]])

        insights, _, _ = svc._analyze_correlation(corr, self.lignes("BTC", "ETH"))

        assert severites(insights)[0] == InsightSeverity.CRITICAL

    def test_sous_07_aucune_alerte_de_diversification(self):
        corr = self.donnees(["BTC", "ETH"], [[1.0, 0.5], [0.5, 1.0]])

        insights, moyenne, _ = svc._analyze_correlation(corr, self.lignes("BTC", "ETH"))

        assert moyenne == 0.5
        assert titres(insights) == []

    def test_les_paires_fortement_correlees_forment_un_cluster(self):
        corr = self.donnees(["BTC", "ETH"], [[1.0, 0.91], [0.91, 1.0]], fortes=[("BTC", "ETH", 0.91)])

        _, _, clusters = svc._analyze_correlation(corr, self.lignes("BTC", "ETH"))

        assert len(clusters) == 1
        assert set(clusters[0]["assets"]) == {"BTC", "ETH"}
        assert clusters[0]["avg_corr"] == 0.91

    def test_une_paire_prolonge_le_cluster_auquel_elle_touche(self):
        # BTC-ETH forme un groupe, puis ETH-SOL y rattache SOL : trois actifs,
        # un seul cluster.
        corr = self.donnees(
            ["BTC", "ETH", "SOL"],
            [[1.0, 0.91, 0.88], [0.91, 1.0, 0.9], [0.88, 0.9, 1.0]],
            fortes=[("BTC", "ETH", 0.91), ("ETH", "SOL", 0.90)],
        )

        _, _, clusters = svc._analyze_correlation(corr, self.lignes("BTC", "ETH", "SOL"))

        assert len(clusters) == 1
        assert set(clusters[0]["assets"]) == {"BTC", "ETH", "SOL"}

    def test_deux_clusters_deja_formes_fusionnent_quand_une_paire_les_relie(self):
        """Le cas précédent ne passe **pas** par la fusion.

        BTC-ETH puis ETH-SOL empruntent la branche « un seul côté connu », qui
        se contente d'agrandir le groupe existant. La fusion proprement dite ne
        s'exécute que lorsque les deux actifs d'une paire appartiennent déjà à
        deux groupes distincts — ici BTC-ETH et SOL-ADA, réunis par ETH-SOL.
        Sans ce troisième cas, supprimer la fusion ne casse rien.
        """
        symboles = ["BTC", "ETH", "SOL", "ADA"]
        matrice = [
            [1.0, 0.91, 0.87, 0.86],
            [0.91, 1.0, 0.90, 0.88],
            [0.87, 0.90, 1.0, 0.92],
            [0.86, 0.88, 0.92, 1.0],
        ]
        corr = self.donnees(
            symboles,
            matrice,
            fortes=[("BTC", "ETH", 0.91), ("SOL", "ADA", 0.92), ("ETH", "SOL", 0.90)],
        )

        _, _, clusters = svc._analyze_correlation(corr, self.lignes(*symboles))

        assert len(clusters) == 1
        assert set(clusters[0]["assets"]) == {"BTC", "ETH", "SOL", "ADA"}

    def test_une_correlation_sous_le_seuil_de_cluster_est_ignoree(self):
        # Le seuil est 0,85 : une paire à 0,80 apparaît dans
        # `strongly_correlated` sans pour autant former un cluster.
        corr = self.donnees(["BTC", "ETH"], [[1.0, 0.80], [0.80, 1.0]], fortes=[("BTC", "ETH", 0.80)])

        _, _, clusters = svc._analyze_correlation(corr, self.lignes("BTC", "ETH"))

        assert clusters == []
