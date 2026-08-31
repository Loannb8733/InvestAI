"""Un ajustement interne n'est pas un retrait : il ne doit jamais être miroité.

Le mirroring part du principe qu'un TRANSFER_OUT non apparié est un retrait vers le
cold wallet, et lui crée une entrée miroir sur Tangem. Or beaucoup de TRANSFER_OUT
sont des écritures internes de réconciliation : mise à zéro d'un solde fantôme,
balayage de poussière, ajustement manuel, ou les lignes de réconciliation ajoutées
par scripts/reconcile_missing_entries.py.

Constaté en production le 2026-06-07 : une opération de NETTOYAGE sur Kraken,
Binance et Crypto.com a produit 5 entrées fantômes sur Tangem — 109 529 PEPE,
25,21 USDT, 2,52 USDG, 0,0086 DOGE — alors que l'utilisateur n'avait jamais détenu
ces actifs sur ce wallet. Le nettoyage d'un fantôme en créait un ailleurs.

Au moment du correctif, 51 ajustements internes n'avaient pas encore de miroir :
le risque était latent, pas passé.
"""

from pathlib import Path

import pytest

from app.main import INTERNAL_ADJUSTMENT_NOTE_PREFIXES, INTERNAL_NOTE_PATTERNS

_MAIN_SRC = (Path(__file__).resolve().parents[2] / "app" / "main.py").read_text(encoding="utf-8")


class TestLibellesCouverts:
    @pytest.mark.parametrize(
        "note",
        [
            "Ajustement balance Binance",
            "Ajustement balance Kraken",
            "Phantom holding zeroed 2026-06-07: Kraken reported 0",
            "Solde zéro sur Binance (vendu/converti)",
            "Dust sweep 2026-06-26: Crypto.com BTC zeroed",
            "Manual adjustment 2026-06-07: 25.21 USDT lost",
            "Réconciliation : entrée antérieure à la fenêtre de synchronisation",
            "Cale 2026-06-26: retire le fantome auto-mirror Kraken",
        ],
    )
    def test_chaque_libelle_observe_est_exclu(self, note):
        assert any(note.startswith(p) for p in INTERNAL_ADJUSTMENT_NOTE_PREFIXES)


class TestRetraitsReelsPreserves:
    @pytest.mark.parametrize(
        "note",
        [
            "Retrait Binance → Tangem",
            "Retrait Kraken → Tangem",
            "trade_id:withdrawal_FTdX0hl-sbTJA7M4IQsEzX",
            "",
        ],
    )
    def test_un_vrai_retrait_reste_miroite(self, note):
        # Ceux-là DOIVENT continuer à produire un miroir : c'est la fonctionnalité.
        assert not any(note.startswith(p) for p in INTERNAL_ADJUSTMENT_NOTE_PREFIXES)


class TestClauseSql:
    def test_un_motif_par_prefixe(self):
        assert len(INTERNAL_NOTE_PATTERNS) == len(INTERNAL_ADJUSTMENT_NOTE_PREFIXES)
        for prefix, pattern in zip(INTERNAL_ADJUSTMENT_NOTE_PREFIXES, INTERNAL_NOTE_PATTERNS):
            assert pattern == prefix + "%"

    def test_les_deux_requetes_de_mirroring_filtrent(self):
        # Celle du démarrage et celle de l'endpoint admin.
        assert _MAIN_SRC.count("LIKE ANY(:internal_note_patterns)") == 2

    def test_le_parametre_est_bien_passe(self):
        assert _MAIN_SRC.count('{"internal_note_patterns": INTERNAL_NOTE_PATTERNS}') == 2

    def test_les_libelles_ne_sont_jamais_concatenes_dans_le_sql(self):
        # Ils voyagent en paramètre lié : aucun n'apparaît dans une chaîne SQL.
        for prefix in INTERNAL_ADJUSTMENT_NOTE_PREFIXES:
            assert f"LIKE '{prefix}" not in _MAIN_SRC

    def test_les_notes_nulles_sont_gerees(self):
        # Sans COALESCE, `NULL LIKE ANY(...)` vaut NULL, le NOT le laisse NULL, et un
        # retrait réel sans notes cesserait d'être miroité.
        assert "COALESCE(t.notes, '') LIKE ANY(:internal_note_patterns)" in _MAIN_SRC
