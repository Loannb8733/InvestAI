"""Filet sur l'actif auquel une conversion crypto-à-crypto est rattachée.

`_extract_base_asset` lit un symbole de conversion — « DOGEPEPE », deux cryptos
accolées, sans devise de cotation sur laquelle découper — et décide quel actif
du portefeuille la transaction vient mouvementer. Elle vivait en fermeture
interne dans `_sync_detailed_transactions` (615 lignes non couvertes) ; elle est
maintenant une fonction de module pour être éprouvée directement.

L'enjeu : une réponse fausse ne lève rien. `_get_or_create_asset` **crée** l'actif
manquant, et la conversion s'inscrit sur un actif fantôme portant des quantités
réelles. 81 conversions sont déjà passées par ce chemin.

Ce filet épingle le comportement actuel, son devinage compris — voir
`test_le_repli_tronque_a_quatre_lettres`, qui documente NEW-54 plutôt que de le
corriger en douce.
"""

import pytest

from app.tasks.sync_exchanges import _extract_base_asset

RIEN: set = set()


class TestCorrespondanceAvecLesActifsConnus:
    def test_l_actif_connu_le_plus_long_l_emporte(self):
        """« DOGEPEPE » commence par « DOGE » comme par « DO ».

        Sans le tri par longueur décroissante, l'ordre du dictionnaire
        déciderait — et « DO » rattacherait la conversion au mauvais actif.
        """
        assert _extract_base_asset("DOGEPEPE", {"DO", "DOGE"}) == "DOGE"

    def test_un_actif_connu_de_six_lettres_est_reconnu_entier(self):
        # Sans cette branche, le repli tronquerait PENDLE à « PEND ».
        assert _extract_base_asset("PENDLEUSDC", {"PENDLE", "USDC"}) == "PENDLE"

    def test_un_actif_connu_de_cinq_lettres_est_reconnu_entier(self):
        assert _extract_base_asset("KAITOSOL", {"KAITO", "SOL"}) == "KAITO"

    def test_seul_le_prefixe_compte_pas_la_presence_ailleurs(self):
        # « PEPE » est la moitié droite : elle ne doit pas être retenue.
        assert _extract_base_asset("DOGEPEPE", {"PEPE"}) != "PEPE"

    def test_les_variantes_earn_sont_normalisees_avant_la_comparaison(self):
        """« LDBTC » est le BTC placé en Earn chez Binance.

        La normalisation passe en premier : sans elle, « LDBTC » ne
        correspondrait à aucun actif connu et le repli rendrait « LDBT ».
        """
        assert _extract_base_asset("LDBTC", {"BTC"}) == "BTC"

    def test_une_variante_wrapped_est_ramenee_a_son_sous_jacent(self):
        assert _extract_base_asset("WBTC", {"BTC"}) == "BTC"


class TestSansCorrespondance:
    """NEW-54 : renoncer plutôt que deviner.

    Un repli devinait une longueur de préfixe — 4, puis 3, 5, 6 — quand aucun
    actif connu ne correspondait. Il tronquait donc tout actif de cinq ou six
    lettres converti pour la **première** fois : `PENDLEPEPE` devenait `PEND`,
    et `_get_or_create_asset` créait l'actif fantôme, qui portait ensuite des
    quantités réelles.

    Le devinage traitait correctement les actifs nouveaux de trois ou quatre
    lettres ; ce cas est perdu, et c'est l'échange consenti : une conversion
    ignorée se signale dans le journal et se saisit à la main, un actif fantôme
    pollue le prix de revient sans se voir.
    """

    @pytest.mark.parametrize("symbole", ["PENDLEPEPE", "KAITOSOL", "BTCPEPE", "BTC", "OBSCURXYZ"])
    def test_un_symbole_sans_actif_connu_ne_rend_rien(self, symbole):
        assert _extract_base_asset(symbole, RIEN) is None

    def test_un_actif_connu_est_toujours_reconnu(self):
        # La règle ne coupe que le devinage : la reconnaissance par préfixe,
        # elle, reste entière — c'est elle qui traite les 81 conversions
        # réelles.
        assert _extract_base_asset("PENDLEPEPE", {"PENDLE"}) == "PENDLE"
        assert _extract_base_asset("BTCPEPE", {"BTC"}) == "BTC"

    def test_un_symbole_vide_ne_rend_rien(self):
        assert _extract_base_asset("", RIEN) is None
