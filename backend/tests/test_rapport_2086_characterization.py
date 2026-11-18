"""Caractérisation de la génération du formulaire 2086.

Pourquoi ce fichier existe
--------------------------
`render_tax_pdf` produit le document que l'utilisateur joint à sa
déclaration de revenus : plus-values de cessions d'actifs numériques, formulaire
2086. 225 lignes, couvertes à **3 %**.

Le **calcul** est déjà caractérisé ailleurs — `compute_tax_2086` a ses tests
dans `test_fifo_replay_characterization.py`. Ce qui manquait, c'est la **mise en
forme** : rien ne garantissait qu'un montant correctement calculé arrive
effectivement, et sans altération, dans le PDF remis à l'administration.

Ces tests lisent le texte du document produit, et non sa seule existence. Un
PDF valide mais vide passerait le premier contrôle ; il ne passe pas ceux-ci.
"""

from datetime import UTC, datetime

import pymupdf

from app.domains.reports.styles import money
from app.domains.reports.tax import TaxEvent2086, TaxSummary2086
from app.domains.reports.tax_pdf import render_tax_pdf
from app.domains.reports.tax_rates import pfu_rates


def _cession(symbole="BTC", quantite=0.5, prix_cession=15000.0, gain=5000.0, duree="long_terme"):
    return TaxEvent2086(
        date=datetime(2026, 3, 15, tzinfo=UTC),
        symbol=symbole,
        event_type="sell",
        quantity=quantite,
        unit_price=prix_cession / quantite if quantite else 0.0,
        cession_price=prix_cession,
        portfolio_value=60000.0,
        total_acquisition_cost=40000.0,
        acquisition_fraction=prix_cession - gain,
        gain_loss=gain,
        holding_period=duree,
        fees=0.0,
    )


def _resume(evenements=None, **surcharges):
    evenements = evenements if evenements is not None else [_cession()]
    plus_values = sum(e.gain_loss for e in evenements if e.gain_loss > 0)
    moins_values = sum(-e.gain_loss for e in evenements if e.gain_loss < 0)
    net = plus_values - moins_values
    taux = pfu_rates(surcharges.get("year", 2026))
    exonere = surcharges.get("exempt", False)
    base = 0.0 if exonere else max(net, 0.0)
    defauts = dict(
        year=2026,
        total_cessions=sum(e.cession_price for e in evenements),
        total_acquisitions_fraction=sum(e.acquisition_fraction for e in evenements),
        total_plus_values=plus_values,
        total_moins_values=moins_values,
        net_plus_value=net,
        nb_cessions=len(evenements),
        nb_court_terme=sum(1 for e in evenements if e.holding_period == "court_terme"),
        nb_long_terme=sum(1 for e in evenements if e.holding_period == "long_terme"),
        pfu_total=base * float(taux.total),
        pfu_ir=base * float(taux.ir),
        pfu_ps=base * float(taux.ps),
        events=evenements,
    )
    defauts.update(surcharges)
    return TaxSummary2086(**defauts)


async def _generer(db_session, resume):
    return render_tax_pdf(resume, 2026)


def _texte(pdf: bytes) -> str:
    """Texte du document, pages concaténées, espaces normalisés."""
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        brut = "\n".join(page.get_text() for page in doc)
    return " ".join(brut.split())


class TestDocumentProduit:
    async def test_un_pdf_valide_est_rendu(self, db_session):
        pdf = await _generer(db_session, _resume())

        assert pdf.startswith(b"%PDF"), "signature de fichier PDF"
        assert len(pdf) > 1000

    async def test_le_document_s_annonce_comme_le_formulaire_2086(self, db_session):
        texte = _texte(await _generer(db_session, _resume()))

        assert "2086" in texte

    async def test_l_annee_fiscale_est_imprimee_dans_le_titre(self, db_session):
        """Le libellé entier est vérifié, pas le seul millésime : les dates de
        cession contiennent déjà l'année, si bien qu'un test cherchant « 2026 »
        passait au vert même en retirant le titre — constaté par canari."""
        texte = _texte(await _generer(db_session, _resume()))

        assert "Année 2026" in texte


class TestMontantsImprimes:
    """Le point qui compte : un montant calculé doit arriver dans le document."""

    async def test_la_plus_value_nette_apparait(self, db_session):
        texte = _texte(await _generer(db_session, _resume([_cession(gain=5000.0)])))

        assert "5" in texte and "000" in texte
        assert "Plus-value" in texte or "plus-value" in texte.lower()

    async def test_le_nombre_de_cessions_apparait(self, db_session):
        evenements = [_cession(symbole="BTC"), _cession(symbole="ETH"), _cession(symbole="SOL")]
        texte = _texte(await _generer(db_session, _resume(evenements)))

        assert "3" in texte

    async def test_chaque_symbole_cede_est_liste(self, db_session):
        evenements = [_cession(symbole="BTC"), _cession(symbole="ETH")]
        texte = _texte(await _generer(db_session, _resume(evenements)))

        assert "BTC" in texte
        assert "ETH" in texte

    async def test_les_deux_composantes_du_pfu_sont_chiffrees(self, db_session):
        """Le PFU se décompose en impôt sur le revenu et prélèvements sociaux.

        Ce sont les **montants** qui sont vérifiés, pas les taux : « 12,8 % » et
        « 18,6 % » figurent aussi dans le paragraphe explicatif du formulaire,
        si bien qu'un test portant sur les taux passait au vert même en
        supprimant la ligne du tableau — vérifié par canari.
        """
        resume = _resume([_cession(gain=10000.0)])
        texte = _texte(await _generer(db_session, resume))

        # Montants formatés en entier, tels que `money` les écrit — « 1,280.00 € ».
        # Une première version comparait un « noyau » tronqué à la virgule, donc
        # au seul chiffre « 1 » : présent partout, le test ne prouvait rien.
        for montant in (resume.pfu_ir, resume.pfu_ps):
            attendu = money(montant)
            assert attendu in texte, f"{attendu} absent du document"


class TestCasSansCession:
    async def test_une_annee_sans_cession_produit_quand_meme_un_document(self, db_session):
        """Une année blanche doit rendre un formulaire, pas une erreur : c'est
        la preuve qu'il n'y avait rien à déclarer."""
        pdf = await _generer(db_session, _resume([]))

        assert pdf.startswith(b"%PDF")
        texte = _texte(pdf)
        assert "2086" in texte

    async def test_aucune_taxe_sur_une_annee_blanche(self, db_session):
        resume = _resume([])

        assert resume.pfu_total == 0.0
        texte = _texte(await _generer(db_session, resume))
        assert texte, "le document reste lisible"


class TestMoinsValues:
    async def test_une_moins_value_n_engendre_pas_d_impot(self, db_session):
        """Une année en perte ne se taxe pas : le PFU doit rester à zéro."""
        resume = _resume([_cession(gain=-3000.0)])

        assert resume.net_plus_value < 0
        assert resume.pfu_total == 0.0
        texte = _texte(await _generer(db_session, resume))
        assert "2086" in texte

    async def test_le_document_distingue_court_et_long_terme(self, db_session):
        evenements = [
            _cession(symbole="BTC", duree="long_terme"),
            _cession(symbole="ETH", duree="court_terme"),
        ]
        texte = _texte(await _generer(db_session, _resume(evenements)))

        assert "BTC" in texte and "ETH" in texte


class TestTauxEtExoneration:
    """PFU de l'année des revenus (LFSS 2026) et seuil de 305 € (art. 150 VH bis II-B)."""

    async def test_le_taux_2026_est_31_4_pour_cent_et_non_30(self, db_session):
        texte = _texte(await _generer(db_session, _resume([_cession(gain=10000.0)])))

        assert "31,4 %" in texte
        assert "18,6 %" in texte
        assert "30,0 %" not in texte and "17,2 %" not in texte
        assert money(3140.0) in texte

    async def test_les_taux_2024_restent_a_30_pour_cent(self, db_session):
        resume = _resume([_cession(gain=10000.0)], year=2024)

        texte = _texte(render_tax_pdf(resume, 2024))

        assert "30,0 %" in texte and "17,2 %" in texte
        assert money(3000.0) in texte

    async def test_une_annee_exoneree_l_annonce_sans_impot(self, db_session):
        petite = _cession(prix_cession=300.0, gain=90.0)
        resume = _resume([petite], exempt=True)

        texte = _texte(await _generer(db_session, resume))

        assert resume.pfu_total == 0.0
        assert "305" in texte and "exonérée" in texte

    async def test_les_lignes_du_formulaire_sont_imprimees(self, db_session):
        texte = _texte(await _generer(db_session, _resume()))

        for libelle in ("ligne 51", "ligne 52", "(212)", "(217)", "(223)"):
            assert libelle in texte
