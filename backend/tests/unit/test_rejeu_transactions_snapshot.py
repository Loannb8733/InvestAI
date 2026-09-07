"""Filet de caractérisation de `_replay_transactions_to_daily_holdings`.

Cette fonction rejoue les transactions jour par jour pour reconstruire les
avoirs, le capital investi et le capital net. Tout l'historique du patrimoine en
découle : la courbe du dashboard, les alertes de variation, les emails
hebdomadaires et le TWR. `snapshot_service` est couvert à 24 % et n'a aucun
fichier de test propre.

Ces tests épinglent le comportement **actuel**. Ce ne sont pas des tests de
spécification : plusieurs règles ci-dessous sont des arbitrages métier qu'il
faudrait confirmer, pas des vérités. Leur rôle est qu'un changement les rende
visibles.

La fonction est pure — pas de base, pas de réseau — donc testable directement
avec de simples doubles de transaction.
"""

from datetime import datetime
from types import SimpleNamespace

from app.models.transaction import TransactionType
from app.services.snapshot_service import snapshot_service


def tx(
    jour: str,
    symbole: str,
    type_tx: TransactionType,
    quantite: float,
    prix: float,
    conversion_rate: float | None = None,
    asset_type: str = "crypto",
):
    """Double minimal : la fonction ne lit que ces attributs."""
    return SimpleNamespace(
        executed_at=datetime.fromisoformat(jour),
        created_at=None,
        symbol=symbole,
        transaction_type=type_tx,
        quantity=quantite,
        price=prix,
        conversion_rate=conversion_rate,
        asset_type=asset_type,
    )


def rejouer(transactions, debut="2026-01-01", fin="2026-01-03"):
    return snapshot_service._replay_transactions_to_daily_holdings(
        transactions,
        datetime.fromisoformat(debut),
        datetime.fromisoformat(fin),
    )


class TestAvoirs:
    def test_un_achat_ajoute_la_quantite_des_son_jour(self):
        avoirs, _, _, _ = rejouer([tx("2026-01-02", "BTC", TransactionType.BUY, 0.5, 40000)])

        assert avoirs["2026-01-01"] == {}
        assert avoirs["2026-01-02"] == {"BTC": 0.5}
        assert avoirs["2026-01-03"] == {"BTC": 0.5}

    def test_les_avoirs_persistent_les_jours_sans_transaction(self):
        avoirs, _, _, _ = rejouer([tx("2026-01-01", "ETH", TransactionType.BUY, 2, 2000)])

        assert avoirs["2026-01-03"] == {"ETH": 2}

    def test_le_symbole_est_normalise_en_majuscules(self):
        avoirs, _, _, types = rejouer([tx("2026-01-01", "btc", TransactionType.BUY, 1, 40000)])

        assert avoirs["2026-01-01"] == {"BTC": 1}
        assert types == {"BTC": "crypto"}

    def test_une_vente_ne_peut_pas_rendre_les_avoirs_negatifs(self):
        """Vendre plus qu'on ne possède ramène à 0, jamais à un négatif.

        Ce test rachète après la vente excessive, parce que le jour de la vente
        ne prouve rien : les avoirs négatifs sont de toute façon écartés par le
        filtre `q > 1e-10`, si bien qu'un solde à -4 et un solde à 0 s'affichent
        tous deux comme vides. C'est l'achat suivant qui les sépare — il repart
        de 0 avec la garde, de -4 sans elle.
        """
        avoirs, _, _, _ = rejouer(
            [
                tx("2026-01-01", "BTC", TransactionType.BUY, 1, 40000),
                tx("2026-01-01", "BTC", TransactionType.SELL, 5, 40000),
                tx("2026-01-02", "BTC", TransactionType.BUY, 2, 40000),
            ]
        )

        assert avoirs["2026-01-01"] == {}
        assert avoirs["2026-01-02"] == {"BTC": 2}

    def test_un_reliquat_infinitesimal_disparait_des_avoirs(self):
        # Seuil à 1e-10 : les arrondis de flottants laissent des poussières de
        # quantité après une vente totale, qui afficheraient un actif fantôme.
        avoirs, _, _, _ = rejouer(
            [
                tx("2026-01-01", "BTC", TransactionType.BUY, 1.0, 40000),
                tx("2026-01-02", "BTC", TransactionType.SELL, 0.9999999999999, 40000),
            ]
        )

        assert "BTC" not in avoirs["2026-01-02"]


class TestOrdreDeRejeu:
    def test_un_achat_precede_une_vente_du_meme_jour(self):
        # Sans cet ordre, la vente ramènerait les avoirs à 0 avant que l'achat
        # ne les crédite, et la quantité finale serait fausse.
        avoirs, _, _, _ = rejouer(
            [
                tx("2026-01-01", "BTC", TransactionType.SELL, 1, 40000),
                tx("2026-01-01", "BTC", TransactionType.BUY, 2, 40000),
            ]
        )

        assert avoirs["2026-01-01"] == {"BTC": 1}


class TestCapitalInvestiEtNet:
    def test_un_achat_augmente_les_deux(self):
        _, investi, net, _ = rejouer([tx("2026-01-01", "BTC", TransactionType.BUY, 0.5, 40000)])

        assert investi["2026-01-01"] == 20000
        assert net["2026-01-01"] == 20000

    def test_une_vente_baisse_le_capital_net_mais_pas_l_investi(self):
        # L'investi est cumulatif : il retrace ce qui a été engagé, pas ce qui
        # reste engagé. Le net, lui, se dégonfle à la revente.
        _, investi, net, _ = rejouer(
            [
                tx("2026-01-01", "BTC", TransactionType.BUY, 1, 40000),
                tx("2026-01-02", "BTC", TransactionType.SELL, 1, 50000),
            ]
        )

        assert investi["2026-01-02"] == 40000
        assert net["2026-01-02"] == -10000

    def test_le_capital_net_peut_devenir_negatif(self):
        # Récupérer plus qu'on n'a investi est un cas valide, et le TWR en a
        # besoin : brider à 0 casserait le calcul de performance.
        _, _, net, _ = rejouer([tx("2026-01-01", "BTC", TransactionType.SELL, 1, 40000)])

        assert net["2026-01-01"] == -40000

    def test_un_airdrop_credite_les_avoirs_sans_toucher_au_capital(self):
        avoirs, investi, net, _ = rejouer([tx("2026-01-01", "SOL", TransactionType.AIRDROP, 10, 100)])

        assert avoirs["2026-01-01"] == {"SOL": 10}
        assert investi["2026-01-01"] == 0
        assert net["2026-01-01"] == 0

    def test_une_recompense_de_staking_ne_compte_pas_comme_investie(self):
        avoirs, investi, _, _ = rejouer([tx("2026-01-01", "ETH", TransactionType.STAKING_REWARD, 0.1, 2000)])

        assert avoirs["2026-01-01"] == {"ETH": 0.1}
        assert investi["2026-01-01"] == 0

    def test_un_transfert_entrant_compte_comme_un_apport(self):
        # Contrairement à l'airdrop, un TRANSFER_IN est traité comme de
        # l'argent apporté. C'est un arbitrage : un transfert depuis un cold
        # wallet déjà comptabilisé le compterait deux fois.
        _, investi, net, _ = rejouer([tx("2026-01-01", "BTC", TransactionType.TRANSFER_IN, 1, 40000)])

        assert investi["2026-01-01"] == 40000
        assert net["2026-01-01"] == 40000

    def test_un_transfert_sortant_retire_les_avoirs_sans_toucher_au_capital(self):
        # L'actif part sur un cold wallet : il quitte les avoirs valorisés mais
        # reste la propriété de l'utilisateur, donc le capital net ne bouge pas.
        avoirs, _, net, _ = rejouer(
            [
                tx("2026-01-01", "BTC", TransactionType.BUY, 1, 40000),
                tx("2026-01-02", "BTC", TransactionType.TRANSFER_OUT, 1, 45000),
            ]
        )

        assert avoirs["2026-01-02"] == {}
        assert net["2026-01-02"] == 40000


class TestConversions:
    def test_un_swap_deplace_les_avoirs_sans_bouger_le_capital(self):
        # Le correctif que ce test tient : CONVERSION_IN créditait autrefois le
        # capital net du montant de la transaction. Or les conversions issues
        # d'une synchronisation arrivent avec price=0, si bien que le IN
        # n'ajoutait rien pendant que le OUT retranchait la valeur réelle —
        # chaque swap vidait le capital net.
        avoirs, investi, net, _ = rejouer(
            [
                tx("2026-01-01", "BTC", TransactionType.BUY, 1, 40000),
                tx("2026-01-02", "BTC", TransactionType.CONVERSION_OUT, 1, 40000),
                tx("2026-01-02", "ETH", TransactionType.CONVERSION_IN, 20, 0),
            ]
        )

        assert avoirs["2026-01-02"] == {"ETH": 20}
        assert investi["2026-01-02"] == 40000
        assert net["2026-01-02"] == 40000

    def test_un_swap_reste_neutre_meme_a_prix_renseigne(self):
        """Le cas précédent nourrit CONVERSION_IN à prix nul, comme le fait une
        synchronisation. Il ne prouve donc rien sur la branche IN : lui faire
        recréditer `quantité × prix` n'ajouterait de toute façon rien.

        Une conversion saisie à la main porte un prix. C'est elle qui distingue
        une branche neutre d'une branche qui recrédite.
        """
        _, investi, net, _ = rejouer(
            [
                tx("2026-01-01", "BTC", TransactionType.BUY, 1, 40000),
                tx("2026-01-02", "BTC", TransactionType.CONVERSION_OUT, 1, 40000),
                tx("2026-01-02", "ETH", TransactionType.CONVERSION_IN, 20, 2000),
            ]
        )

        assert investi["2026-01-02"] == 40000
        assert net["2026-01-02"] == 40000


class TestConversionDeDevise:
    def test_le_taux_capture_convertit_le_montant(self):
        _, investi, _, _ = rejouer(
            [tx("2026-01-01", "AAPL", TransactionType.BUY, 10, 100, conversion_rate=0.9, asset_type="stock")]
        )

        assert investi["2026-01-01"] == 900

    def test_un_taux_absent_ou_nul_vaut_un(self):
        # `if rate else 1.0` : None et 0 tombent tous deux sur 1. Un taux
        # réellement nul annulerait le montant, ce que la valeur 1 évite.
        _, investi_absent, _, _ = rejouer([tx("2026-01-01", "BTC", TransactionType.BUY, 1, 40000)])
        _, investi_nul, _, _ = rejouer([tx("2026-01-01", "BTC", TransactionType.BUY, 1, 40000, conversion_rate=0)])

        assert investi_absent["2026-01-01"] == 40000
        assert investi_nul["2026-01-01"] == 40000


class TestDatesLimites:
    def test_une_transaction_sans_date_est_ignoree(self):
        sans_date = tx("2026-01-01", "BTC", TransactionType.BUY, 1, 40000)
        sans_date.executed_at = None

        avoirs, investi, _, _ = rejouer([sans_date])

        assert avoirs["2026-01-01"] == {}
        assert investi["2026-01-01"] == 0

    def test_le_jour_d_une_transaction_suit_son_fuseau_de_saisie(self):
        """Une transaction du 2 janvier à 1 h UTC+2 — soit le 1er à 23 h UTC —
        est rattachée au **2 janvier**.

        La fonction appelle `replace(tzinfo=None)` avant de formater, mais ce
        `replace` ne change rien au résultat : `strftime("%Y-%m-%d")` lit les
        champs de date tels quels, sans convertir vers UTC. Le retirer laisse
        ces tests verts — il est inerte ici, et seul le comportement observable
        est épinglé.
        """
        aware = tx("2026-01-02", "BTC", TransactionType.BUY, 1, 40000)
        aware.executed_at = datetime.fromisoformat("2026-01-02T01:00:00+02:00")

        avoirs, _, _, _ = rejouer([aware])

        assert avoirs["2026-01-01"] == {}
        assert avoirs["2026-01-02"] == {"BTC": 1}

    def test_une_transaction_hors_fenetre_ne_figure_dans_aucun_jour(self):
        # Elle est bien indexée par date, mais aucun jour parcouru ne
        # correspond : son effet est perdu, y compris sur le capital investi.
        avoirs, investi, _, _ = rejouer([tx("2025-12-01", "BTC", TransactionType.BUY, 1, 40000)])

        assert avoirs["2026-01-01"] == {}
        assert investi["2026-01-03"] == 0
