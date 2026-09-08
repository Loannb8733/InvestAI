"""Filet sur la lecture des noms d'actifs et de paires chez Kraken.

`exchanges/kraken.py` était couvert à **11 %**. Deux de ses fonctions sont
pures et décident de quelque chose de très concret : **sur quel actif** une
transaction importée est enregistrée.

Kraken emploie une nomenclature qui lui est propre — `XXBT` pour le bitcoin,
`ZEUR` pour l'euro, `.S` pour une position stakée. Mal la lire ne produit pas
d'erreur : cela crée une transaction sur un symbole inventé, qui restera dans
le portefeuille sans que rien ne le signale.

Ces tests épinglent le comportement actuel, replis compris.
"""

import pytest

from app.services.exchanges.kraken import KrakenService


@pytest.fixture
def kraken():
    # Les deux méthodes visées sont pures : les identifiants ne servent qu'au
    # constructeur, et aucun appel réseau n'est fait.
    return KrakenService(api_key="cle-de-test", secret_key="c2VjcmV0")


class TestNomsDActifs:
    @pytest.mark.parametrize(
        "brut,attendu",
        [
            ("XXBT", "BTC"),
            ("XBT", "BTC"),
            ("XETH", "ETH"),
            ("XXDG", "DOGE"),
            ("ZEUR", "EUR"),
            ("ZUSD", "USD"),
        ],
    )
    def test_les_noms_historiques_passent_par_la_table(self, kraken, brut, attendu):
        """Le préfixe X marque les cryptos d'origine, Z les monnaies d'État.

        `XXBT` est le bitcoin : Kraken l'appelle XBT, et le préfixe X s'ajoute
        pour les actifs les plus anciens. Le lire « XXBT » créerait une ligne
        sur un symbole qui n'existe nulle part ailleurs.
        """
        assert kraken._normalize_asset(brut) == attendu

    @pytest.mark.parametrize(
        "brut,attendu",
        [("SOL", "SOL"), ("DOT", "DOT"), ("ADA", "ADA"), ("PEPE", "PEPE")],
    )
    def test_les_noms_modernes_passent_tels_quels(self, kraken, brut, attendu):
        assert kraken._normalize_asset(brut) == attendu

    @pytest.mark.parametrize(
        "brut,attendu",
        [
            ("PEPE.S", "PEPE"),
            ("ETH2.S", "ETH"),
            ("DOT.M", "DOT"),
            ("SOL.F", "SOL"),
            ("ADA.B", "ADA"),
            ("KSM.P", "KSM"),
        ],
    )
    def test_les_suffixes_de_staking_sont_retires(self, kraken, brut, attendu):
        """Une position stakée reste le même actif.

        `.S` staké, `.M` marge, `.F` staking flexible, `.B` immobilisé, `.P`
        parachain. Les garder scinderait chaque position en deux lignes — une
        stakée, une libre — dont le total ne correspondrait plus au solde.
        Le cas `ETH2.S` est traité en premier, sans quoi le `.S` seul
        laisserait un `ETH2` orphelin.
        """
        assert kraken._normalize_asset(brut) == attendu

    def test_un_seul_suffixe_est_retire(self, kraken):
        # La boucle s'arrête au premier suffixe reconnu : un nom doublement
        # suffixé n'est pas dépouillé deux fois.
        assert kraken._normalize_asset("PEPE.S.S") == "PEPE.S"

    def test_un_prefixe_double_inconnu_est_simplement_retire(self, kraken):
        assert kraken._normalize_asset("XXNOUVEAU") == "NOUVEAU"

    def test_un_prefixe_simple_ne_tombe_que_sur_un_symbole_plausible(self, kraken):
        """Après `X`, le reste doit ressembler à un symbole — 3 à 5 lettres.

        Sans cette borne, un actif nommé `XY` deviendrait `Y`, et un nom long
        perdrait sa première lettre. Dans le doute, le nom est gardé entier.
        """
        assert kraken._normalize_asset("XTRES_LONG_NOM") == "XTRES_LONG_NOM"


class TestPairesDeCotation:
    @pytest.mark.parametrize(
        "paire,base,cotation",
        [
            ("XXBTZEUR", "BTC", "EUR"),
            ("XETHZEUR", "ETH", "EUR"),
            ("XXBTZUSD", "BTC", "USD"),
            ("SOLEUR", "SOL", "EUR"),
            ("ADAUSD", "ADA", "USD"),
        ],
    )
    def test_une_paire_se_scinde_en_actif_et_devise(self, kraken, paire, base, cotation):
        assert kraken._extract_base_from_pair(paire) == (base, cotation)

    @pytest.mark.parametrize("paire,base", [("ETHXBT", "ETH"), ("XRPXBT", "XRP"), ("ADAXBT", "ADA")])
    def test_une_paire_cotee_en_bitcoin_est_reconnue(self, kraken, paire, base):
        """Corrigé le 2026-09-08 : `XBT` manquait aux devises de cotation.

        Kraken emploie `XBT` — non `BTC` — dans ses paires. Aucune devise de la
        liste ne correspondait donc, et le dernier repli attribuait « EUR » :
        un prix de 0,05 BTC était lu comme 0,05 EUR, trois ordres de grandeur
        plus bas.

        Exposition au moment de la correction : **aucune** transaction Kraken
        en devise autre qu'EUR ou USD. Le défaut était réel mais dormant.
        """
        assert kraken._extract_base_from_pair(paire) == (base, "BTC")

    def test_une_paire_en_stablecoin_est_reconnue(self, kraken):
        assert kraken._extract_base_from_pair("SOLUSDT") == ("SOL", "USDT")

    def test_une_paire_inconnue_retombe_sur_l_euro(self, kraken):
        """Dernier repli : les premiers caractères, et l'euro supposé.

        C'est un pari — le portefeuille est libellé en euros — mais il est
        silencieux : une paire cotée en dollars mal reconnue serait valorisée
        au mauvais cours. Épinglé tel quel.
        """
        base, cotation = kraken._extract_base_from_pair("ABCXYZ")

        assert cotation == "EUR"
        assert base == "ABC"

    def test_une_paire_inconnue_a_prefixe_X_garde_quatre_caracteres(self, kraken):
        # `XXBT…` se découpe sur quatre caractères, non trois : trois
        # donneraient `XXB`, qui n'est aucun actif.
        base, cotation = kraken._extract_base_from_pair("XXBTINCONNU")

        assert base == "BTC"
        assert cotation == "EUR"
