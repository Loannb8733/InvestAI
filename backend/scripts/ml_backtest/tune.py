"""Réglage par horizon sur la validation : correction MAPE κ(h) et facteur d'intervalle z(h).

python tune.py <validation.jsonl>
"""

import sys

import numpy as np
from combine import HORIZONS, ape, load

KAPPAS = np.round(np.arange(0.0, 1.55, 0.1), 2)
Q_LEVELS = (0.90, 0.925, 0.95, 0.96, 0.97, 0.975, 0.98, 0.99)


def var_daily(r: dict, h: int) -> float:
    return r["sd_d"] ** 2 * h


def table(rows: list[dict], h: int, var) -> None:
    symbols = sorted({r["symbol"] for r in rows})
    naive = {s: np.mean([ape(r["p0"], r["actual"][h - 1]) for r in rows if r["symbol"] == s]) for s in symbols}
    print(f"\n-- horizon {h} j : MAPE naïf {np.mean([ape(r['p0'], r['actual'][h - 1]) for r in rows]):.3f}")
    for k in KAPPAS:
        per = {
            s: np.mean([ape(r["p0"] * np.exp(-k * var(r, h)), r["actual"][h - 1]) for r in rows if r["symbol"] == s])
            for s in symbols
        }
        allm = np.mean([ape(r["p0"] * np.exp(-k * var(r, h)), r["actual"][h - 1]) for r in rows])
        worst = max(per[s] / naive[s] for s in symbols)
        bias = np.mean(
            [(r["p0"] * np.exp(-k * var(r, h)) - r["actual"][h - 1]) / r["actual"][h - 1] * 100 for r in rows]
        )
        print(f"κ={k:.1f}  MAPE {allm:.3f}  pire actif {worst:.4f}  biais moyen {bias:+.2f} %")


def quantile_interval(r: dict, h: int, level: float) -> tuple[float, float]:
    rets = r["rets"][h]
    lo, hi = np.quantile(rets, [(1 - level) / 2, 1 - (1 - level) / 2])
    return r["p0"] * float(np.exp(lo)), r["p0"] * float(np.exp(hi))


def intervals(rows: list[dict]) -> None:
    for h in HORIZONS:
        cur = [r["low"][h - 1] <= r["actual"][h - 1] <= r["high"][h - 1] for r in rows]
        curw = np.mean([(r["high"][h - 1] - r["low"][h - 1]) / r["p0"] * 100 for r in rows])
        print(f"\n-- intervalles {h} j : actuel couverture {np.mean(cur):.1%} largeur {curw:.1f} %")
        for q in Q_LEVELS:
            iv = [quantile_interval(r, h, q) for r in rows]
            cov = np.mean([lo <= r["actual"][h - 1] <= hi for (lo, hi), r in zip(iv, rows, strict=True)])
            wid = np.mean([(hi - lo) / r["p0"] * 100 for (lo, hi), r in zip(iv, rows, strict=True)])
            print(f"quantiles {q:.3f} : couverture {cov:.1%} largeur {wid:.1f} %")


if __name__ == "__main__":
    rows = load(sys.argv[1], "binance_daily.json")
    for h in HORIZONS:
        table(rows, h, lambda r, hh: r["var_h"][hh])
    print("\n==== variance = variance quotidienne × h")
    for h in HORIZONS:
        table(rows, h, var_daily)
    intervals(rows)
