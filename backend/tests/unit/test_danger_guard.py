"""Garde-fou des scripts de maintenance destructifs.

`recalc_avg_price.py` et `recalculate_quantities.py` réécrivent des colonnes
financières à partir d'hypothèses qui ne tiennent plus :

- ils recalculent `avg_buy_price` SANS lire `conversion_rate`, rétablissant le prix
  brut en devise étrangère comme s'il s'agissait d'euros — l'erreur même que FIN-01
  corrige ;
- `recalculate_quantities` écrase en plus `asset.quantity` par la somme signée de
  l'historique, alors que celui-ci n'est jamais exhaustif (sorties de cold wallet
  non récupérables, fenêtre de sync limitée).

Ils se lançaient en une commande, commitaient sans confirmation, et leur nom ne
disait rien de leur dangerosité. D'où un consentement explicite obligatoire.

Fonctions pures : ni base, ni réseau.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from scripts._danger_guard import CONSENT_FLAG, consent_granted, require_consent

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


class TestConsentement:
    def test_absent_par_defaut(self):
        assert consent_granted([]) is False
        assert consent_granted(["script.py"]) is False

    def test_reconnu_quelle_que_soit_la_position(self):
        assert consent_granted(["script.py", CONSENT_FLAG]) is True
        assert consent_granted([CONSENT_FLAG, "autre"]) is True

    def test_un_drapeau_approchant_ne_suffit_pas(self):
        # Ni une troncature, ni une variante : le consentement doit être délibéré.
        for presque in ["--i-know", "--yes", "-y", "--force", "--i-know-what-im-doing-really"]:
            assert consent_granted(["script.py", presque]) is False


class TestBlocage:
    def test_sans_consentement_le_script_est_interrompu(self):
        with pytest.raises(SystemExit) as e:
            require_consent("x.py", "danger", "alternative", argv=[])
        assert e.value.code == 1

    def test_avec_consentement_il_continue(self):
        # Ne lève pas : le script poursuit son exécution.
        require_consent("x.py", "danger", "alternative", argv=[CONSENT_FLAG])

    def test_le_message_dit_le_danger_et_l_alternative(self, capsys):
        with pytest.raises(SystemExit):
            require_consent("x.py", "CASSE TOUT", "faire ceci", argv=[])
        sortie = capsys.readouterr().out
        assert "CASSE TOUT" in sortie
        assert "faire ceci" in sortie
        assert CONSENT_FLAG in sortie


class TestScriptsReellementArmes:
    """Les deux scripts dangereux appellent bien le garde-fou avant d'agir."""

    @pytest.mark.parametrize("nom", ["recalc_avg_price.py", "recalculate_quantities.py"])
    def test_le_script_importe_et_appelle_le_garde(self, nom):
        src = (_SCRIPTS / nom).read_text(encoding="utf-8")
        assert "require_consent" in src, f"{nom} n'appelle pas le garde-fou"
        # L'appel doit précéder l'exécution, donc figurer dans le bloc __main__.
        bloc_main = src.split('if __name__ == "__main__":')[-1]
        assert "require_consent(" in bloc_main, f"{nom} : le garde n'est pas dans le bloc __main__"

    @pytest.mark.parametrize("nom", ["recalc_avg_price.py", "recalculate_quantities.py"])
    def test_execution_sans_drapeau_sort_en_erreur(self, nom):
        # Sans le drapeau, le script doit s'arrêter AVANT toute connexion à la base.
        r = subprocess.run(
            [sys.executable, str(_SCRIPTS / nom)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(_SCRIPTS.parent),
        )
        assert r.returncode == 1, f"{nom} ne s'est pas arrêté (code {r.returncode})"
        assert "EXÉCUTION BLOQUÉE" in r.stdout
