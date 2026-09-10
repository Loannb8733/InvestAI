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


class TestRepliParDevinage:
    def test_le_repli_tronque_a_quatre_lettres(self):
        """La verrue, épinglée telle quelle (NEW-54).

        Quand aucun actif connu ne correspond, la fonction devine une longueur :
        4, puis 3, 5, 6. Un actif de cinq ou six lettres converti pour la
        **première** fois — donc absent du portefeuille — se retrouve tronqué,
        et `_get_or_create_asset` crée « PEND » de toutes pièces.

        Aucun actif de ce genre n'existe aujourd'hui en base : les six symboles
        longs concernés (PENDLE, KAITO…) étaient déjà connus quand leur
        première conversion est arrivée. Le défaut est latent, pas actif.
        """
        assert _extract_base_asset("PENDLEPEPE", RIEN) == "PEND"
        assert _extract_base_asset("KAITOSOL", RIEN) == "KAIT"

    def test_la_longueur_quatre_est_essayee_avant_la_longueur_trois(self):
        # L'ordre [4, 3, 5, 6] n'est pas croissant : c'est un pari sur la
        # longueur de ticker la plus fréquente, pas une règle.
        assert _extract_base_asset("BTCPEPE", RIEN) == "BTCP"

    def test_un_symbole_de_trois_lettres_tombe_sur_la_longueur_trois(self):
        assert _extract_base_asset("BTC", RIEN) == "BTC"

    def test_un_prefixe_non_alphabetique_est_refuse(self):
        """« 1INCH » et consorts : le repli n'accepte que des lettres.

        Ici la longueur 4 donnerait « BTC1 », rejetée, et la longueur 3 rend
        « BTC ».
        """
        assert _extract_base_asset("BTC1PEPE", RIEN) == "BTC"

    def test_un_prefixe_en_minuscules_est_refuse(self):
        assert _extract_base_asset("dogepepe", RIEN) is None

    def test_un_symbole_trop_court_ne_rend_rien(self):
        # Aucune des longueurs tentées ne tient dans deux caractères.
        assert _extract_base_asset("AB", RIEN) is None

    def test_un_symbole_vide_ne_rend_rien(self):
        assert _extract_base_asset("", RIEN) is None
