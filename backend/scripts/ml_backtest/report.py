"""Tableaux avant / après : MAPE par horizon et par actif, couverture et largeur des intervalles.

« avant » : ce que le code évalué a servi (``ens``, ``low``, ``high`` du backtest). « après » : la prévision ancrée
de ``app.ml.forecasting.floor`` recalculée sur le même historique, ou servie directement si le backtest a tourné
avec ce code. « variante B » : la même, avec la correction MAPE ``MAPE_SHIFT_PER_LOG_DAY = 0,15``.

    python report.py <results.jsonl> [--data fichier.json]
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(os.environ.get("BT_BACKEND", HERE.parents[1])).resolve()))
os.environ.setdefault("SECRET_KEY", "backtest_only_dummy_secret_key_1234567890")
os.environ.setdefault("FERNET_KEY", "icQAqvAxUzGIr5HCiFPkDICQtKw_tIwRDbCnZW0HW6M=")

from app.ml.forecasting import floor  # noqa: E402

HORIZONS = (1, 7, 30)
VARIANT_B = 0.15


def ape(pred: float, act: float) -> float:
    return abs(pred - act) / act * 100


def _history(closes: dict[str, float], origin: str) -> list[float]:
    return [closes[d] for d in sorted(d for d in closes if d <= origin)][-floor.HISTORY_DAYS :]


def collect(path: str, data_file: str) -> dict:
    raw = json.loads((HERE / "data" / data_file).read_text())
    closes = {s: dict(zip(v["dates"], v["close"], strict=True)) for s, v in raw.items()}
    rows = [json.loads(line) for line in open(path) if line.strip()]
    stats: dict = defaultdict(list)
    for r in rows:
        history = _history(closes[r["symbol"]], r["origin"])
        after, low, high = floor.anchored(history, 30)
        shift, floor.MAPE_SHIFT_PER_LOG_DAY = floor.MAPE_SHIFT_PER_LOG_DAY, VARIANT_B
        variant, _, _ = floor.anchored(history, 30)
        floor.MAPE_SHIFT_PER_LOG_DAY = shift
        for h in HORIZONS:
            act, i = r["actual"][h - 1], h - 1
            for key in ("all", r["symbol"]):
                stats[(key, h, "naïf")].append(ape(r["p0"], act))
                stats[(key, h, "avant")].append(ape(r["ens"][i], act))
                stats[(key, h, "après")].append(ape(after[i], act))
                stats[(key, h, "variante B")].append(ape(variant[i], act))
                stats[(key, h, "cov avant")].append(r["low"][i] <= act <= r["high"][i])
                stats[(key, h, "cov après")].append(low[i] <= act <= high[i])
                stats[(key, h, "larg avant")].append((r["high"][i] - r["low"][i]) / r["p0"] * 100)
                stats[(key, h, "larg après")].append((high[i] - low[i]) / r["p0"] * 100)
    stats["n"] = len(rows)
    stats["symbols"] = sorted({r["symbol"] for r in rows})
    return stats


def main(path: str, data_file: str) -> None:
    s = collect(path, data_file)
    m = lambda key, h, col: float(np.mean(s[(key, h, col)]))  # noqa: E731
    print(f"{s['n']} prévisions\n")
    print(
        "| Horizon | MAPE naïf | MAPE avant | MAPE après | variante B | Couverture avant | Couverture après | Largeur avant | Largeur après |"
    )
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for h in HORIZONS:
        print(
            f"| {h} j | {m('all', h, 'naïf'):.2f} % | {m('all', h, 'avant'):.2f} % | {m('all', h, 'après'):.2f} % "
            f"| {m('all', h, 'variante B'):.2f} % | {m('all', h, 'cov avant'):.0%} | {m('all', h, 'cov après'):.0%} "
            f"| {m('all', h, 'larg avant'):.1f} % | {m('all', h, 'larg après'):.1f} % |"
        )
    print(
        "\n| Actif | MAPE 1 j avant → après | MAPE 7 j avant → après | MAPE 30 j avant → après | après ≤ naïf partout | variante B ≤ naïf partout |"
    )
    print("|---|---:|---:|---:|:---:|:---:|")
    for sym in s["symbols"]:
        cells = [f"{m(sym, h, 'avant'):.2f} → {m(sym, h, 'après'):.2f} %" for h in HORIZONS]
        floor_ok = all(m(sym, h, "après") <= m(sym, h, "naïf") + 1e-9 for h in HORIZONS)
        b_ok = all(m(sym, h, "variante B") <= m(sym, h, "naïf") + 1e-9 for h in HORIZONS)
        print(
            f"| {sym.replace('USDT', '')} | "
            + " | ".join(cells)
            + f" | {'oui' if floor_ok else 'non'} | {'oui' if b_ok else 'non'} |"
        )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[sys.argv.index("--data") + 1] if "--data" in sys.argv else "binance_daily.json")
