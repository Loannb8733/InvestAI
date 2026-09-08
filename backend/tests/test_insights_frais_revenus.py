"""Filet de caractérisation des frais payés et des revenus passifs.

Deux méthodes d'`insights_service` que l'utilisateur consulte pour savoir ce
que lui coûte sa gestion et ce qu'elle lui rapporte. Le module était couvert à
31 % après le filet sur l'optimisation fiscale.

Elles lisent la base : le filet s'appuie sur la fixture `db_session` du projet.

Comportement actuel épinglé, pas spécification approuvée — et deux écarts
mesurés y sont nommés sans être corrigés.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.services.insights_service import InsightsService


@pytest.fixture
def service():
    return InsightsService()


async def portefeuille(db_session, user, nom="Test") -> Portfolio:
    pf = Portfolio(user_id=user.id, name=nom)
    db_session.add(pf)
    await db_session.flush()
    return pf


async def actif(db_session, pf, symbole="BTC") -> Asset:
    a = Asset(
        portfolio_id=pf.id,
        symbol=symbole,
        name=symbole,
        asset_type=AssetType.CRYPTO,
        quantity=Decimal("1"),
        avg_buy_price=Decimal("40000"),
    )
    db_session.add(a)
    await db_session.flush()
    return a


def mouvement(
    asset,
    *,
    type_tx=TransactionType.BUY,
    quantite="1",
    prix="40000",
    frais="0",
    devise_frais="EUR",
    quand="2026-03-15",
    exchange="Binance",
):
    return Transaction(
        asset_id=asset.id,
        transaction_type=type_tx,
        quantity=Decimal(quantite),
        price=Decimal(prix),
        fee=Decimal(frais),
        fee_currency=devise_frais,
        exchange=exchange,
        executed_at=datetime.fromisoformat(quand).replace(tzinfo=timezone.utc),
    )


class TestAnalyseDesFrais:
    async def test_sans_portefeuille_le_resultat_est_vide(self, db_session, regular_user, service):
        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["total_fees"] == 0
        assert res["by_exchange"] == {}

    async def test_un_portefeuille_sans_actif_rend_le_meme_vide(self, db_session, regular_user, service):
        await portefeuille(db_session, regular_user)
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["total_fees"] == 0

    async def test_les_frais_sont_ventiles_par_plateforme_actif_type_et_mois(self, db_session, regular_user, service):
        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf, "BTC")
        db_session.add(mouvement(btc, frais="10", quand="2026-01-10"))
        db_session.add(mouvement(btc, frais="5", quand="2026-02-10", exchange="Kraken"))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["total_fees"] == 15.0
        assert res["nb_transactions_with_fees"] == 2
        assert res["by_exchange"] == {"Binance": 10.0, "Kraken": 5.0}
        assert res["by_asset"] == {"BTC": 15.0}
        assert res["by_month"] == {"2026-01": 10.0, "2026-02": 5.0}

    async def test_une_transaction_sans_frais_est_ignoree(self, db_session, regular_user, service):
        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf)
        db_session.add(mouvement(btc, frais="0"))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["nb_transactions_with_fees"] == 0

    async def test_une_plateforme_absente_devient_inconnu(self, db_session, regular_user, service):
        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf)
        db_session.add(mouvement(btc, frais="3", exchange=""))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["by_exchange"] == {"Inconnu": 3.0}

    async def test_les_ventilations_sont_triees_par_montant_decroissant(self, db_session, regular_user, service):
        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf, "BTC")
        eth = await actif(db_session, pf, "ETH")
        db_session.add(mouvement(btc, frais="2", exchange="A"))
        db_session.add(mouvement(eth, frais="9", exchange="B"))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert list(res["by_exchange"]) == ["B", "A"]
        assert list(res["by_asset"]) == ["ETH", "BTC"]

    async def test_la_moyenne_mensuelle_porte_sur_la_duree_couverte(self, db_session, regular_user, service):
        """Corrigé le 2026-09-08 (NEW-27) : le diviseur était le nombre de mois
        **ayant porté des frais**, pas la durée.

        Six euros en janvier et six en décembre couvrent douze mois : la
        moyenne vaut **1 EUR**. L'ancien calcul divisait par 2 et annonçait
        6 EUR — il répondait à « combien coûte un mois actif », non à « combien
        cela me coûte par mois », ce que le libellé laisse entendre.

        Deux mois espacés, pas un seul : sur un mois unique les deux calculs
        donnent le même chiffre, et le test ne prouverait rien.
        """
        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf)
        db_session.add(mouvement(btc, frais="6", quand="2026-01-10"))
        db_session.add(mouvement(btc, frais="6", quand="2026-12-10"))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["total_fees"] == 12.0
        assert res["avg_monthly_fee"] == 1.0

    async def test_un_mois_unique_reste_son_propre_denominateur(self, db_session, regular_user, service):
        # Rien à étaler : la durée couverte vaut un mois.
        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf)
        db_session.add(mouvement(btc, frais="12", quand="2026-01-10"))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["avg_monthly_fee"] == 12.0

    async def test_une_transaction_sans_date_ne_fausse_pas_la_duree(self, db_session, regular_user, service):
        """Les mouvements non datés tombent dans un mois « ? ».

        Cette clé ne situe rien sur l'axe du temps : elle est écartée du calcul
        de durée, sans quoi elle allongerait arbitrairement le dénominateur.
        """
        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf)
        sans_date = mouvement(btc, frais="4", quand="2026-01-10")
        sans_date.executed_at = None
        db_session.add(sans_date)
        db_session.add(mouvement(btc, frais="8", quand="2026-01-10"))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["avg_monthly_fee"] == 12.0

    async def test_les_frais_sont_ramenes_en_euros_avant_d_etre_sommes(
        self, db_session, regular_user, service, monkeypatch
    ):
        """Corrigé le 2026-09-08 (NEW-21) : le total sommait des devises brutes.

        « 1 EUR + 1 USDC + 0,001 BTC = 2,001 » mélangeait trois unités. Chaque
        frais est désormais ramené en euros avant d'entrer dans le total et
        dans les ventilations :

        - l'euro passe tel quel ;
        - **0,001 BTC** est valorisé au prix unitaire de sa propre transaction —
          40 000 € — soit **40 €**, contre 0,001 auparavant ;
        - l'USDC, jeton distinct de l'actif échangé, prend son cours.

        Le cours est fixé ici : sans cela, le test dépendrait du marché du jour.
        """
        from app.services import insights_service as module

        async def cours(symbole, type_actif):
            return {"price": 0.9} if symbole.upper() == "USDC" else None

        monkeypatch.setattr(module.price_service, "get_price", cours)

        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf)
        db_session.add(mouvement(btc, frais="1", devise_frais="EUR"))
        db_session.add(mouvement(btc, frais="1", devise_frais="USDC"))
        db_session.add(mouvement(btc, frais="0.001", devise_frais="BTC"))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["total_fees"] == 41.9  # 1 + 0,9 + 40
        assert res["nb_frais_non_convertis"] == 0

    async def test_un_frais_sans_cours_reste_signale_plutot_qu_efface(
        self, db_session, regular_user, service, monkeypatch
    ):
        """Faute de cours, le montant est gardé tel quel et compté à part.

        Le remettre à zéro minorerait silencieusement les frais — le défaut
        qu'on vient de corriger, dans l'autre sens. `nb_frais_non_convertis`
        dit combien de lignes restent hétérogènes.
        """
        from app.services import insights_service as module

        async def aucun_cours(symbole, type_actif):
            return None

        monkeypatch.setattr(module.price_service, "get_price", aucun_cours)

        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf)
        db_session.add(mouvement(btc, frais="2", devise_frais="BNB"))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["total_fees"] == 2.0
        assert res["nb_frais_non_convertis"] == 1
        assert res["recent_fees"][0]["fee_convertie"] is False

    async def test_un_frais_fiat_suit_le_taux_capte_a_l_execution(self, db_session, regular_user, service):
        """Des frais en USD sur une transaction en USD prennent son taux.

        C'est le taux du jour de l'opération, pas celui d'aujourd'hui : les
        frais historiques ne bougent plus avec le marché.
        """
        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf)
        tx = mouvement(btc, frais="10", devise_frais="USD")
        tx.currency = "USD"
        tx.conversion_rate = Decimal("0.92")
        db_session.add(tx)
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["total_fees"] == 9.2

    async def test_la_ventilation_par_actif_est_tronquee_aux_dix_premiers(self, db_session, regular_user, service):
        # Le total reste complet : la somme des dix lignes affichées ne le
        # retrouve donc pas sur un portefeuille plus large.
        pf = await portefeuille(db_session, regular_user)
        for i in range(12):
            a = await actif(db_session, pf, f"A{i:02d}")
            db_session.add(mouvement(a, frais=str(i + 1)))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert len(res["by_asset"]) == 10
        assert res["total_fees"] == 78.0  # 1+2+…+12
        assert sum(res["by_asset"].values()) == 75.0  # les deux plus petites manquent

    async def test_les_frais_recents_sont_limites_a_vingt(self, db_session, regular_user, service):
        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf)
        for i in range(25):
            db_session.add(mouvement(btc, frais="1", quand=f"2026-01-{i % 28 + 1:02d}"))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["nb_transactions_with_fees"] == 25
        assert len(res["recent_fees"]) == 20


class TestRevenusPassifs:
    async def test_sans_portefeuille_le_resultat_est_vide(self, db_session, regular_user, service):
        res = await service.get_passive_income(db_session, str(regular_user.id))

        assert res["total_income"] == 0
        assert res["nb_events"] == 0

    async def test_les_recompenses_de_staking_et_airdrops_sont_comptes(self, db_session, regular_user, service):
        pf = await portefeuille(db_session, regular_user)
        eth = await actif(db_session, pf, "ETH")
        db_session.add(mouvement(eth, type_tx=TransactionType.STAKING_REWARD, quantite="0.1", prix="2000"))
        db_session.add(mouvement(eth, type_tx=TransactionType.AIRDROP, quantite="10", prix="5"))
        await db_session.commit()

        res = await service.get_passive_income(db_session, str(regular_user.id))

        assert res["total_income"] == 250.0  # 200 + 50
        assert res["nb_events"] == 2
        assert res["by_type"] == {"staking_reward": 200.0, "airdrop": 50.0}

    async def test_les_dividendes_et_interets_ne_sont_pas_comptes(self, db_session, regular_user, service):
        """La docstring annonce « dividends, staking rewards, interest ».

        `passive_types` ne contient pourtant que `STAKING_REWARD` et `AIRDROP` :
        un dividende d'action ou un intérêt obligataire n'apparaît nulle part
        dans le suivi des revenus passifs. Les deux types existent, et tout le
        reste du code les traite bien comme des revenus — ils comptent dans les
        entrées du TRI (`analytics_math._XIRR_INFLOW_TYPES`) et créditent les
        quantités à l'import.

        Exposition mesurée : **zéro transaction** de ces deux types en base de
        développement — l'écart est réel mais dormant. Il se réveillerait au
        premier dividende d'action enregistré.
        """
        pf = await portefeuille(db_session, regular_user)
        aapl = await actif(db_session, pf, "AAPL")
        db_session.add(mouvement(aapl, type_tx=TransactionType.DIVIDEND, quantite="1", prix="100"))
        db_session.add(mouvement(aapl, type_tx=TransactionType.INTEREST, quantite="1", prix="50"))
        await db_session.commit()

        res = await service.get_passive_income(db_session, str(regular_user.id))

        assert res["total_income"] == 0
        assert res["nb_events"] == 0

    async def test_un_revenu_sans_prix_est_valorise_a_zero(self, db_session, regular_user, service):
        # Un airdrop de jeton non coté compte comme un événement mais
        # n'augmente pas le revenu.
        pf = await portefeuille(db_session, regular_user)
        tok = await actif(db_session, pf, "TOK")
        db_session.add(mouvement(tok, type_tx=TransactionType.AIRDROP, quantite="100", prix="0"))
        await db_session.commit()

        res = await service.get_passive_income(db_session, str(regular_user.id))

        assert res["nb_events"] == 1
        assert res["total_income"] == 0

    async def test_le_filtre_par_annee_restreint_la_periode(self, db_session, regular_user, service):
        pf = await portefeuille(db_session, regular_user)
        eth = await actif(db_session, pf, "ETH")
        db_session.add(
            mouvement(eth, type_tx=TransactionType.STAKING_REWARD, quantite="1", prix="100", quand="2025-06-01")
        )
        db_session.add(
            mouvement(eth, type_tx=TransactionType.STAKING_REWARD, quantite="1", prix="200", quand="2026-06-01")
        )
        await db_session.commit()

        tout = await service.get_passive_income(db_session, str(regular_user.id))
        en_2026 = await service.get_passive_income(db_session, str(regular_user.id), year=2026)

        assert tout["total_income"] == 300.0
        assert en_2026["total_income"] == 200.0

    async def test_la_projection_annuelle_extrapole_les_trois_derniers_mois_percus(
        self, db_session, regular_user, service
    ):
        """Les « trois derniers mois » sont les trois derniers **ayant produit un
        revenu**, non les trois derniers mois calendaires.

        Un portefeuille qui a touché 100 EUR par mois en 2025 puis plus rien
        depuis projette donc 1 200 EUR pour l'année à venir, sur la foi de
        données vieilles d'un an.
        """
        pf = await portefeuille(db_session, regular_user)
        eth = await actif(db_session, pf, "ETH")
        # Un premier mois maigre, puis trois mois pleins : la fenêtre de trois
        # doit ignorer le premier. Une série de trois mois seulement ne
        # prouverait rien — `[-3:]` y vaut la liste entière.
        for mois, montant in (("01", "10"), ("02", "100"), ("03", "100"), ("04", "100")):
            db_session.add(
                mouvement(
                    eth, type_tx=TransactionType.STAKING_REWARD, quantite="1", prix=montant, quand=f"2025-{mois}-01"
                )
            )
        await db_session.commit()

        res = await service.get_passive_income(db_session, str(regular_user.id))

        assert res["projected_annual"] == 1200.0  # 100 x 12, le mois maigre écarté
        # 310 EUR sur quatre mois couverts (janvier à avril) : 77,5.
        assert res["avg_monthly"] == 77.5

    async def test_la_moyenne_des_revenus_porte_aussi_sur_la_duree_couverte(self, db_session, regular_user, service):
        # Même correction que pour les frais : deux versements espacés d'un an
        # couvrent treize mois, pas deux.
        pf = await portefeuille(db_session, regular_user)
        eth = await actif(db_session, pf, "ETH")
        for quand in ("2025-01-01", "2026-01-01"):
            db_session.add(
                mouvement(eth, type_tx=TransactionType.STAKING_REWARD, quantite="1", prix="650", quand=quand)
            )
        await db_session.commit()

        res = await service.get_passive_income(db_session, str(regular_user.id))

        assert res["total_income"] == 1300.0
        assert res["avg_monthly"] == 100.0  # 1300 / 13

    async def test_l_historique_est_limite_a_trente_evenements(self, db_session, regular_user, service):
        pf = await portefeuille(db_session, regular_user)
        eth = await actif(db_session, pf, "ETH")
        for i in range(35):
            db_session.add(
                mouvement(
                    eth,
                    type_tx=TransactionType.STAKING_REWARD,
                    quantite="1",
                    prix="10",
                    quand=f"2026-01-{i % 28 + 1:02d}",
                )
            )
        await db_session.commit()

        res = await service.get_passive_income(db_session, str(regular_user.id))

        assert res["nb_events"] == 35
        assert len(res["history"]) == 30
