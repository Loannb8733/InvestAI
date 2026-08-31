"""Conversion des frais réglés en crypto, et fiabilité du flag `forex_stale`.

Les frais d'exchange sont souvent payés en crypto (BTC, ETH, BNB…). Or
`_get_rate_with_cache` interrogeait un convertisseur **forex**, qui ne connaît que
les monnaies fiat et renvoie None pour BTC. Le code retombait alors sur la constante
de dernier recours — 1,0 — donc 0,0001 BTC était compté 0,0001 € au lieu de ~6,80 €,
et `forex_stale` restait levé en permanence.

Un flag toujours allumé ne signale plus rien : il ne pouvait plus servir à avertir
d'un vrai incident de change. Mesuré avant/après sur des données réelles :
True -> False, pour un impact de moins d'un euro sur le P&L.

Ordre des correctifs : la devise des frais a été assainie AVANT de brancher la
conversion crypto. Une transaction Bitstack portait `fee = 0,29` avec
`fee_currency = 'BTC'` sur un achat de 0,0001234 BTC — soit 2 350 fois la quantité
achetée. C'étaient 0,29 €. Convertir d'abord aurait valorisé ces frais à ~19 700 €.
"""

from pathlib import Path

_SRC = (Path(__file__).resolve().parents[2] / "app" / "services" / "metrics_service.py").read_text(encoding="utf-8")


class TestConversionCrypto:
    def test_le_prix_crypto_est_tente_avant_la_constante(self):
        # L'ordre compte : la constante 1,0 est le dernier recours, pas le premier.
        avant_constante = _SRC.split("_HARDCODED_FALLBACK_RATES.get(from_ccy")[0]
        assert "_crypto_unit_price(from_ccy, to_ccy)" in avant_constante

    def test_un_prix_de_marche_n_est_pas_marque_perime(self):
        bloc = _SRC.split("crypto_rate = await _crypto_unit_price")[1][:400]
        assert "return crypto_rate, False" in bloc, (
            "un prix crypto temps réel est une donnée fraîche : le marquer stale " "rendrait le flag inutilisable"
        )

    def test_le_helper_degrade_sans_bruit(self):
        # Un symbole inconnu ne doit ni lever ni polluer les logs d'avertissement :
        # l'appelant poursuit son cheminement normal.
        helper = _SRC.split("async def _crypto_unit_price")[1].split("async def _get_rate_with_cache")[0]
        assert "return None" in helper
        assert "except Exception" in helper
        assert "logger.debug" in helper, "un symbole non-crypto est un cas normal, pas un avertissement"

    def test_il_demande_bien_un_prix_crypto(self):
        helper = _SRC.split("async def _crypto_unit_price")[1].split("async def _get_rate_with_cache")[0]
        assert 'get_price(symbol, "crypto"' in helper


class TestOrdreDeResolution:
    def test_la_chaine_complete_est_respectee(self):
        """live forex -> cache -> table ECB persistée -> prix crypto -> constante."""
        bloc = _SRC.split("async def _get_rate_with_cache")[1].split("if target != ")[0]
        positions = [
            bloc.index("get_forex_rate"),
            bloc.index("get_cached_forex_rate"),
            bloc.index("_fx_last_known"),
            bloc.index("_crypto_unit_price"),
            bloc.index("_HARDCODED_FALLBACK_RATES"),
        ]
        assert positions == sorted(positions), "l'ordre de repli des taux a changé"

    def test_la_constante_reste_marquee_perimee(self):
        fin = _SRC.split("_HARDCODED_FALLBACK_RATES.get(from_ccy")[1][:400]
        assert (
            "return fallback, True" in fin
        ), "une valeur devinée doit rester signalée, sinon l'UI la présente comme un vrai cours"
