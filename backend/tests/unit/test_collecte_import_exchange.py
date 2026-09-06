"""Les deux transformations pures de la collecte d'un import d'exchange.

Elles portent la logique la plus subtile de la phase de collecte — une fusion
de soldes et un appariement approximatif — et vivaient au milieu d'un bloc de
1 121 lignes, donc sans le moindre test.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.services.exchange_import_collection import dedupliquer_convert_contre_fiat, normaliser_balances_earn
from app.services.exchanges.base import ExchangeBalance, ExchangeFiatOrder

QUAND = datetime(2026, 3, 15, 10, 30, 0, tzinfo=timezone.utc)


def _solde(symbole, total, libre=None, bloque="0"):
    total = Decimal(total)
    return ExchangeBalance(
        symbol=symbole,
        free=Decimal(libre) if libre is not None else total,
        locked=Decimal(bloque),
        total=total,
    )


def _ordre(symbole, quantite, quand=QUAND, oid="o1"):
    return ExchangeFiatOrder(
        order_id=oid,
        crypto_symbol=symbole,
        fiat_currency="EUR",
        side="buy",
        crypto_amount=Decimal(quantite),
        fiat_amount=Decimal("1000"),
        price=Decimal("50000"),
        fee=Decimal("0"),
        status="completed",
        timestamp=quand,
    )


class TestNormalisationDesSoldesEarn:
    """Binance expose l'épargne sous un symbole dérivé : LDUSDC pour de l'USDC
    placé. Sans fusion, le rapprochement voit deux actifs pour une seule
    détention, et croit le solde de base insuffisant."""

    def test_un_symbole_ordinaire_traverse_sans_changement(self):
        soldes, place = normaliser_balances_earn([_solde("BTC", "1.5")])

        assert set(soldes) == {"BTC"}
        assert soldes["BTC"].total == Decimal("1.5")
        assert place == {}

    def test_une_variante_seule_prend_le_nom_de_base(self):
        """Un actif entièrement placé n'a pas de solde de base à rejoindre."""
        soldes, place = normaliser_balances_earn([_solde("LDUSDC", "500")])

        assert set(soldes) == {"USDC"}
        assert soldes["USDC"].total == Decimal("500")
        assert place == {"USDC": 500.0}

    def test_variante_et_base_sont_additionnees(self):
        soldes, place = normaliser_balances_earn([_solde("USDC", "200"), _solde("LDUSDC", "500")])

        assert set(soldes) == {"USDC"}
        assert soldes["USDC"].total == Decimal("700")
        assert place == {"USDC": 500.0}, "seule la part placée est comptée comme immobilisée"

    def test_l_ordre_de_rencontre_ne_change_pas_le_total(self):
        """La variante peut précéder sa base dans la liste rendue par l'API."""
        avant, _ = normaliser_balances_earn([_solde("LDUSDC", "500"), _solde("USDC", "200")])
        apres, _ = normaliser_balances_earn([_solde("USDC", "200"), _solde("LDUSDC", "500")])

        assert avant["USDC"].total == apres["USDC"].total == Decimal("700")

    def test_deux_variantes_du_meme_actif_s_additionnent(self):
        """Un même actif peut être placé sur deux produits — `LDUSDC` et
        `USDCU` mènent tous deux à `USDC`. Les parts placées se cumulent."""
        soldes, place = normaliser_balances_earn(
            [_solde("USDC", "100"), _solde("LDUSDC", "300"), _solde("USDCU", "50")]
        )

        assert soldes["USDC"].total == Decimal("450")
        assert place["USDC"] == 350.0, "les deux placements comptent, pas seulement le dernier"

    def test_les_parts_libre_et_bloquee_suivent(self):
        soldes, _ = normaliser_balances_earn(
            [
                _solde("USDC", "100", libre="60", bloque="40"),
                _solde("LDUSDC", "50", libre="50"),
            ]
        )

        assert soldes["USDC"].free == Decimal("110")
        assert soldes["USDC"].locked == Decimal("40")

    def test_plusieurs_actifs_restent_distincts(self):
        soldes, place = normaliser_balances_earn([_solde("BTC", "1"), _solde("ADAU", "1000"), _solde("ETH", "2")])

        assert set(soldes) == {"BTC", "ADA", "ETH"}
        assert place == {"ADA": 1000.0}

    def test_liste_vide(self):
        assert normaliser_balances_earn([]) == ({}, {})


class TestDeduplicationConvertContreFiat:
    """`fiat/payments` et `convert/tradeFlow` décrivent le même achat en euros
    sous deux identifiants. Sans ce tri, chaque achat par carte compte double."""

    def test_un_ordre_identique_est_ecarte(self):
        fiat = [_ordre("BTC", "0.02")]
        convert = [_ordre("BTC", "0.02", oid="c1")]

        assert dedupliquer_convert_contre_fiat(convert, fiat) == []

    def test_une_minute_d_ecart_est_toleree(self):
        """Les deux API datent le même achat à quelques secondes près."""
        fiat = [_ordre("BTC", "0.02", quand=QUAND)]
        convert = [_ordre("BTC", "0.02", quand=QUAND + timedelta(minutes=1), oid="c1")]

        assert dedupliquer_convert_contre_fiat(convert, fiat) == []

    def test_une_minute_d_ecart_dans_l_autre_sens_aussi(self):
        fiat = [_ordre("BTC", "0.02", quand=QUAND)]
        convert = [_ordre("BTC", "0.02", quand=QUAND - timedelta(minutes=1), oid="c1")]

        assert dedupliquer_convert_contre_fiat(convert, fiat) == []

    def test_au_dela_de_la_tolerance_l_ordre_est_conserve(self):
        """Deux achats du même montant à cinq minutes d'écart sont deux achats."""
        fiat = [_ordre("BTC", "0.02", quand=QUAND)]
        convert = [_ordre("BTC", "0.02", quand=QUAND + timedelta(minutes=5), oid="c1")]

        assert len(dedupliquer_convert_contre_fiat(convert, fiat)) == 1

    def test_un_symbole_different_n_est_pas_un_doublon(self):
        fiat = [_ordre("BTC", "0.02")]
        convert = [_ordre("ETH", "0.02", oid="c1")]

        assert len(dedupliquer_convert_contre_fiat(convert, fiat)) == 1

    def test_une_quantite_differente_n_est_pas_un_doublon(self):
        fiat = [_ordre("BTC", "0.02")]
        convert = [_ordre("BTC", "0.03", oid="c1")]

        assert len(dedupliquer_convert_contre_fiat(convert, fiat)) == 1

    def test_les_zeros_de_fin_ne_font_pas_deux_quantites(self):
        """`0.020` et `0.02` sont le même montant : la comparaison passe par la
        forme normalisée du Decimal."""
        fiat = [_ordre("BTC", "0.020")]
        convert = [_ordre("BTC", "0.02", oid="c1")]

        assert dedupliquer_convert_contre_fiat(convert, fiat) == []

    def test_sans_ordre_fiat_rien_n_est_ecarte(self):
        convert = [_ordre("BTC", "0.02", oid="c1"), _ordre("ETH", "1", oid="c2")]

        assert len(dedupliquer_convert_contre_fiat(convert, [])) == 2

    def test_seuls_les_doublons_partent(self):
        fiat = [_ordre("BTC", "0.02")]
        convert = [_ordre("BTC", "0.02", oid="c1"), _ordre("ETH", "1", oid="c2")]

        restants = dedupliquer_convert_contre_fiat(convert, fiat)
        assert [o.crypto_symbol for o in restants] == ["ETH"]

    def test_l_ordre_d_origine_est_preserve(self):
        convert = [
            _ordre("BTC", "1", oid="c1"),
            _ordre("ETH", "2", oid="c2"),
            _ordre("SOL", "3", oid="c3"),
        ]

        restants = dedupliquer_convert_contre_fiat(convert, [])
        assert [o.order_id for o in restants] == ["c1", "c2", "c3"]
