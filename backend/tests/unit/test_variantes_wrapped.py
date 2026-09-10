"""Un jeton dont le nom commence par W n'est pas un jeton « wrapped ».

Pourquoi c'est une règle et pas un détail
-----------------------------------------
`_normalize_earn_variant` retirait un « W » initial dès que le symbole dépassait
trois caractères. Cela traite correctement WBTC ou WETH — mais mutile toutes les
cryptos dont le nom commence par W :

    WAVES → AVES     WAXP → AXP     WEMIX → EMIX     WING → ING

Un actif acheté sous l'un de ces symboles aurait été enregistré sous un autre.
La substitution est silencieuse et sans trace : rien ne permet de la rattraper
après coup, et le prix récupéré serait celui d'un jeton sans rapport.

Le ticket d'audit citait WIF et WLD. Tous deux échappaient en réalité à la règle
par leur longueur (trois caractères) : le défaut était réel, mais pas sur les
symboles annoncés — d'où l'intérêt de le mesurer avant de le corriger.

Une table explicite remplace la règle de préfixe. « LD » et « BF » la gardent :
ce sont des familles de produits Binance (LDBTC, BFUSD), pas des débuts de noms.
"""

import pytest

from app.tasks.sync_exchanges import _normalize_earn_variant


class TestJetonsWrapped:
    @pytest.mark.parametrize(
        "symbole,attendu",
        [
            ("WBTC", "BTC"),
            ("WETH", "ETH"),
            ("WBETH", "BETH"),
            ("WSOL", "SOL"),
            ("WMATIC", "MATIC"),
        ],
    )
    def test_les_vrais_wrapped_sont_ramenes_au_sous_jacent(self, symbole, attendu):
        assert _normalize_earn_variant(symbole) == attendu


class TestCryptosCommencantParW:
    @pytest.mark.parametrize("symbole", ["WAVES", "WAXP", "WEMIX", "WING", "WHITE", "WIF", "WLD", "WOO", "WAN"])
    def test_elles_ne_sont_jamais_alterees(self, symbole):
        """Ce sont des jetons à part entière, pas des enveloppes."""
        assert _normalize_earn_variant(symbole) == symbole, (
            f"{symbole} altéré : l'actif serait enregistré sous un autre symbole, "
            "avec le prix d'un jeton sans rapport"
        )


class TestProduitsBinance:
    @pytest.mark.parametrize("symbole,attendu", [("LDBTC", "BTC"), ("LDETH", "ETH"), ("BFUSD", "USD")])
    def test_les_prefixes_de_famille_restent_traites(self, symbole, attendu):
        assert _normalize_earn_variant(symbole) == attendu

    @pytest.mark.parametrize("symbole,attendu", [("ADAU", "ADA"), ("SUIU", "SUI"), ("OMKA", "OM"), ("BTCUS", "BTC")])
    def test_les_vrais_suffixes_earn_restent_traites(self, symbole, attendu):
        assert _normalize_earn_variant(symbole) == attendu


class TestJetonsAuxSuffixesTrompeurs:
    """Le « W » avait un jumeau du côté des suffixes (NEW-55).

    La règle acceptait tout suffixe d'un ou deux caractères alphanumériques
    après un nom de base connu. Elle emportait avec elle des jetons entiers :
    Ether.fi, Solv Protocol, Omni Network, OMG Network. Un achat d'ETHFI serait
    venu grossir la position ETH — deux actifs sans rapport, quantités et prix
    de revient mêlés, impossibles à démêler ensuite.

    Le correctif suit celui du « W » : une liste explicite de suffixes.
    """

    @pytest.mark.parametrize(
        "symbole,confondu_avec",
        [
            ("ETHFI", "ETH"),
            ("SOLV", "SOL"),
            ("OMNI", "OM"),
            ("OMG", "OM"),
            ("ADAX", "ADA"),
            ("INJX", "INJ"),
            ("SUIA", "SUI"),
            ("TAOX", "TAO"),
            ("LINKA", "LINK"),
        ],
    )
    def test_ils_ne_sont_jamais_ramenes_a_leur_prefixe(self, symbole, confondu_avec):
        assert (
            _normalize_earn_variant(symbole) == symbole
        ), f"{symbole} confondu avec {confondu_avec} : les deux positions seraient fusionnées"

    def test_la_liste_des_suffixes_est_explicite(self):
        import inspect

        source = inspect.getsource(_normalize_earn_variant)
        assert "SUFFIXES_EARN" in source, "la liste explicite a disparu"
        assert (
            "len(suffix) <= 2" not in source
        ), "la règle de longueur est revenue : elle confondrait à nouveau ETHFI avec ETH"


class TestFormeDeLaRegle:
    def test_la_liste_des_wrapped_est_explicite(self):
        import inspect

        source = inspect.getsource(_normalize_earn_variant)
        assert "variantes_wrapped" in source, "la table explicite a disparu"
        assert '"W"' not in source.split("variantes_wrapped")[0], (
            "le préfixe « W » est revenu dans la liste des préfixes : " "il mutilerait à nouveau WAVES, WAXP, WEMIX…"
        )
