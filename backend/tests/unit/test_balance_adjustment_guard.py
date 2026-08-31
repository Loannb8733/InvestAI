"""Un ajustement de solde ne doit jamais annuler un mouvement déjà enregistré.

La réconciliation de solde compare notre quantité à celle de l'exchange et écrit un
TRANSFER_IN/OUT pour l'écart. Mais quand un trade vient d'être importé sans que le
solde local l'ait encore intégré, l'écart observé EST ce trade — et l'ajustement
l'annule.

Constaté en production le 2026-08-04 : quatre achats sur Kraken (BTC 0,00332921,
ETH 0,02996601, PAXG 0,00689502, SOL 0,37863) ont chacun été suivis d'un
« Ajustement balance » de quantité exactement égale et de sens opposé. L'historique
perdait les achats, le solde les gardait, et l'écart se lisait ensuite comme un
« historique incomplet » — au point qu'une réconciliation ultérieure a empilé une
troisième écriture, faisant chuter le P&L affiché de 214 €.

Fonction pure : ni DB, ni HTTP, ni Docker.
"""

import pytest

from app.tasks.sync_exchanges import contradicts_recent_trade


class TestCasReelDu4Aout:
    @pytest.mark.parametrize(
        "achat",
        [0.00332921, 0.02996601, 0.00689502, 0.37863000],
    )
    def test_l_ajustement_qui_annule_un_achat_est_bloque(self, achat):
        # L'ajustement est de sens opposé : le solde local est en avance sur l'app.
        assert contradicts_recent_trade(-achat, [achat]) is True

    def test_sens_inverse_aussi(self):
        assert contradicts_recent_trade(0.00332921, [0.00332921]) is True


class TestVraisTransfertsPreserves:
    def test_un_transfert_sans_trade_correspondant_passe(self):
        assert contradicts_recent_trade(-0.5, [0.00332921, 0.02996601]) is False

    def test_aucun_mouvement_recent(self):
        assert contradicts_recent_trade(-0.5, []) is False

    def test_quantites_proches_mais_distinctes(self):
        # 10 % d'écart : ce n'est pas le même mouvement, l'ajustement est légitime.
        assert contradicts_recent_trade(-0.11, [0.10]) is False


class TestTolerance:
    def test_ecart_relatif_infime_reconnu(self):
        # La quantité stockée peut différer du dernier chiffre après arrondi.
        assert contradicts_recent_trade(-0.003329213100, [0.003329209400]) is True

    def test_tolerance_ne_capture_pas_un_ordre_de_grandeur(self):
        assert contradicts_recent_trade(-1.0, [0.001]) is False


class TestRobustesse:
    def test_ecart_nul(self):
        assert contradicts_recent_trade(0, [0.5]) is False

    @pytest.mark.parametrize("valeur", [None, 0, -1])
    def test_quantites_invalides_ignorees(self, valeur):
        assert contradicts_recent_trade(-0.5, [valeur]) is False

    def test_une_seule_correspondance_suffit(self):
        assert contradicts_recent_trade(-0.5, [0.1, 0.2, 0.5, 0.9]) is True


class TestToutesLesEcrituresSontDatees:
    """Second volet de FIN-03 : une transaction sans `executed_at` casse le FIFO.

    Le moteur trie par `(executed_at ?? epoch, ...)` : une date nulle place la ligne
    en 1970, donc rejouée AVANT tout achat, sur un stock vide. Elle ne retire alors
    aucun coût, alors que la somme signée la décompte — d'où deux moteurs qui
    divergent sur les mêmes données. 199 lignes étaient dans ce cas en production.

    On vérifie les trois écritures qui en manquaient, repérées par leur libellé :
    chacune doit avoir un `executed_at` dans les lignes qui précèdent immédiatement.
    """

    # (libellé dans le code, nom lisible)
    ECRITURES = [
        ('notes=f"Ajustement balance', "ajustement de balance"),
        ('notes=f"Import initial depuis', "import initial"),
        ('notes=f"Solde zéro sur', "mise à zéro de solde"),
    ]

    def _source(self):
        from pathlib import Path

        return (
            (Path(__file__).resolve().parents[2] / "app" / "tasks" / "sync_exchanges.py")
            .read_text(encoding="utf-8")
            .split("\n")
        )

    @pytest.mark.parametrize("motif,nom", ECRITURES)
    def test_l_ecriture_est_datee(self, motif, nom):
        lignes = self._source()
        trouve = [i for i, l in enumerate(lignes) if motif in l]
        assert trouve, f"écriture « {nom} » introuvable — le libellé a-t-il changé ?"
        for i in trouve:
            # Les champs d'un même Transaction(...) tiennent dans les ~15 lignes amont.
            fenetre = "\n".join(lignes[max(0, i - 15) : i + 2])
            # `executed_at=` avec le signe égal : un commentaire mentionnant
            # « executed_at » ne doit pas suffire à valider le test (piège rencontré).
            assert "executed_at=" in fenetre, (
                f"« {nom} » (ligne {i + 1}) est créée sans executed_at : le FIFO la "
                "rejouerait à l'epoch, avant tout achat, sans retirer de coût."
            )
