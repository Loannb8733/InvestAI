"""Filet sur les deux fonctions pures du tableau de bord.

`_compute_period_twr` produit **le** chiffre de performance affiché en tête du
tableau de bord : le rendement pondéré dans le temps, celui qui neutralise les
dépôts et les retraits pour ne montrer que ce que les placements ont rapporté.
`_ensure_json_safe` est ce qui empêche un `NaN` sorti d'une division de traverser
la réponse et de casser le rendu côté navigateur.

`endpoints/dashboard.py` est couvert à 36 %, et aucun test ne nommait ces deux
fonctions. Elles ne touchent ni la base ni le réseau : rien ne justifiait qu'elles
restent muettes.
"""

from decimal import Decimal

import pytest

from app.api.v1.endpoints.dashboard import _compute_period_twr, _ensure_json_safe


def serie(*couples) -> list:
    """(valeur, capital net) chronologiques, comme les rend la table des snapshots."""
    return [{"value": v, "net_capital": c} for v, c in couples]


class TestSerieTropCourte:
    @pytest.mark.parametrize("points", [[], None, [{"value": 100, "net_capital": 0}]])
    def test_moins_de_deux_points_ne_donne_pas_de_rendement(self, points):
        """Un rendement se mesure entre deux instants ; un seul n'en fait pas une période.

        `None` plutôt que `0.0` : l'écran distingue « pas encore mesurable » de
        « n'a rien rapporté ».
        """
        assert _compute_period_twr(points) is None


class TestSansMouvementDeCapital:
    def test_une_hausse_simple_se_lit_directement(self):
        assert _compute_period_twr(serie((100, 0), (110, 0))) == 10.0

    def test_une_baisse_aussi(self):
        assert _compute_period_twr(serie((100, 0), (80, 0))) == -20.0

    def test_les_sous_periodes_se_composent_au_lieu_de_s_additionner(self):
        """+10 % puis +10 % font +21 %, non +20 %.

        C'est toute la raison d'être d'un rendement pondéré dans le temps :
        chaque sous-période s'applique au capital que la précédente a laissé.
        """
        assert _compute_period_twr(serie((100, 0), (110, 0), (121, 0))) == 21.0

    def test_une_hausse_suivie_d_une_baisse_symetrique_ne_revient_pas_a_zero(self):
        # +50 % puis −50 % laissent −25 % : la baisse porte sur un capital plus gros.
        assert _compute_period_twr(serie((100, 0), (150, 0), (75, 0))) == -25.0


class TestAvecFluxExternes:
    def test_un_depot_ne_compte_pas_comme_une_performance(self):
        """Le cœur du calcul.

        Le portefeuille passe de 100 à 210, mais 100 sont un versement : la
        performance n'est que de 10 %. Sans retrait du flux, l'écran annoncerait
        +110 % pour un simple virement.
        """
        assert _compute_period_twr(serie((100, 100), (210, 200))) == 10.0

    def test_un_retrait_non_plus(self):
        # 100 → 60 après un retrait de 50 : la performance est de +10 %, pas −40 %.
        assert _compute_period_twr(serie((100, 100), (60, 50))) == 10.0

    def test_un_versement_sans_gain_ne_rapporte_rien(self):
        assert _compute_period_twr(serie((100, 100), (150, 150))) == 0.0

    def test_le_flux_se_lit_sur_la_variation_du_capital_net_pas_sur_sa_valeur(self):
        # Deux séries de même performance mais de capital net différent doivent
        # rendre le même chiffre : seule la variation compte.
        assert _compute_period_twr(serie((100, 0), (110, 0))) == _compute_period_twr(serie((100, 5000), (110, 5000)))


class TestGardeFous:
    def test_une_sous_periode_explosive_est_plafonnee(self):
        """Un facteur 50 sur un jour trahit une donnée trouée, pas un gain.

        Le ratio est ramené à 10, soit +900 % au plus par sous-période — assez
        pour rester visible à l'écran comme une anomalie, pas assez pour rendre
        le chiffre absurde.
        """
        assert _compute_period_twr(serie((100, 0), (5000, 0))) == 900.0

    def test_une_valeur_nulle_annule_le_rendement_de_toute_la_periode(self):
        """Le comportement à connaître, épinglé tel quel.

        Un ratio nul remet le produit à zéro : le rendement de la période entière
        tombe à −100 %, et il n'en remonte pas — la sous-période suivante part
        d'une valeur nulle, donc elle est sautée, et le produit reste à zéro.

        Un seul jour où l'instantané a échoué suffirait donc à afficher −100 %
        sur un portefeuille intact. Aucun des 222 instantanés en base n'est à
        zéro : le cas est latent. Le corriger — sauter la sous-période plutôt
        que l'annuler — changerait la définition du calcul, ce n'est pas une
        décision de test.
        """
        assert _compute_period_twr(serie((100, 0), (0, 0), (100, 0), (200, 0))) == -100.0

    def test_une_valeur_de_depart_nulle_fait_sauter_la_sous_periode(self):
        # Sans cette garde, la division par zéro remonterait en erreur 500.
        # La garde s'écrit `> 0` là où `!= 0` suffirait : la valeur d'un
        # portefeuille n'est jamais négative, les deux formes se valent ici.
        assert _compute_period_twr(serie((0, 0), (100, 0), (110, 0))) == 10.0

    def test_une_perte_superieure_au_capital_est_ramenee_a_zero(self):
        # Un retrait mal horodaté peut rendre (valeur − flux) négatif ; le
        # rendement s'arrête à −100 %, il ne descend pas plus bas.
        assert _compute_period_twr(serie((100, 0), (10, 200))) == -100.0

    def test_une_cle_absente_vaut_zero(self):
        assert _compute_period_twr([{"value": 100}, {"value": 110}]) == 10.0

    def test_une_cle_nulle_vaut_zero(self):
        assert _compute_period_twr([{"value": 100, "net_capital": None}, {"value": 110, "net_capital": None}]) == 10.0

    def test_le_resultat_est_arrondi_au_centieme(self):
        assert _compute_period_twr(serie((100, 0), (103.33333, 0))) == 3.33


class TestReponseJsonSaine:
    def test_un_decimal_devient_un_nombre(self):
        """`json.dumps` refuse un `Decimal` : la réponse partirait en erreur 500."""
        assert _ensure_json_safe(Decimal("12.34")) == 12.34
        assert isinstance(_ensure_json_safe(Decimal("12.34")), float)

    @pytest.mark.parametrize("valeur", [float("nan"), float("inf"), float("-inf")])
    def test_un_nombre_non_fini_devient_zero(self, valeur):
        """Ils sortent d'une division par zéro et JSON ne sait pas les écrire.

        Python les sérialise en `NaN` / `Infinity`, que `JSON.parse` refuse :
        le navigateur reçoit une réponse illisible et le tableau de bord reste
        vide, sans message.
        """
        assert _ensure_json_safe(valeur) == 0.0

    def test_les_nombres_finis_traversent_intacts(self):
        assert _ensure_json_safe(3.14) == 3.14
        assert _ensure_json_safe(-0.0) == 0.0

    def test_la_conversion_descend_dans_les_structures_imbriquees(self):
        entree = {"total": Decimal("10"), "lignes": [{"perf": float("nan")}, {"perf": Decimal("2.5")}]}

        assert _ensure_json_safe(entree) == {"total": 10.0, "lignes": [{"perf": 0.0}, {"perf": 2.5}]}

    def test_un_tuple_devient_une_liste(self):
        # JSON n'a pas de tuple ; le rendre tel quel laisserait le sérialiseur
        # s'en charger, ou échouer selon l'implémentation.
        resultat = _ensure_json_safe((Decimal("1"), Decimal("2")))

        assert resultat == [1.0, 2.0]
        assert isinstance(resultat, list)

    @pytest.mark.parametrize("valeur", ["texte", None, True, 42])
    def test_les_autres_types_ne_sont_pas_touches(self, valeur):
        assert _ensure_json_safe(valeur) is valeur
