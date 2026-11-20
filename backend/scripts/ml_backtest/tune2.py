"""κ adaptatif par actif (validation glissante sur son année passée) et multiplicateur d'intervalle m(h).

python tune2.py <results.jsonl> [--data fichier]
"""

import sys

import numpy as np
from combine import HORIZONS, ape, load

KAPPAS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0)
LEVEL = 0.95


def var(r: dict, h: int) -> float:
    return r["sd_d"] ** 2 * h


def helps(r: dict, h: int, k: float) -> bool:
    growth = np.exp(r["rets"][h])
    shifted = np.mean(np.abs(np.exp(-k * var(r, h)) - growth) / growth)
    naive = np.mean(np.abs(1 - growth) / growth)
    return bool(shifted < naive)


def point(r: dict, h: int, k: float, adaptive: bool) -> float:
    if adaptive and not helps(r, h, k):
        return r["p0"]
    return r["p0"] * float(np.exp(-k * var(r, h)))


def kappa_table(rows: list[dict]) -> None:
    symbols = sorted({r["symbol"] for r in rows})
    for h in HORIZONS:
        naive = {s: np.mean([ape(r["p0"], r["actual"][h - 1]) for r in rows if r["symbol"] == s]) for s in symbols}
        print(f"\n-- {h} j : naïf {np.mean([ape(r['p0'], r['actual'][h - 1]) for r in rows]):.3f}")
        for k in KAPPAS:
            for adaptive in (False, True):
                preds = [(r, point(r, h, k, adaptive)) for r in rows]
                per = {s: np.mean([ape(p, r["actual"][h - 1]) for r, p in preds if r["symbol"] == s]) for s in symbols}
                worst = max(per[s] / naive[s] for s in symbols)
                used = np.mean([p != r["p0"] for r, p in preds])
                tag = "adaptatif" if adaptive else "fixe     "
                print(
                    f"κ={k:.1f} {tag} MAPE {np.mean([ape(p, r['actual'][h - 1]) for r, p in preds]):.3f}  pire actif {worst:.4f}  appliqué {used:.0%}"
                )


def band(r: dict, h: int, m: float) -> tuple[float, float]:
    lo, hi = np.quantile(r["rets"][h], [(1 - LEVEL) / 2, 1 - (1 - LEVEL) / 2])
    return r["p0"] * float(np.exp(m * lo)), r["p0"] * float(np.exp(m * hi))


def multipliers(rows: list[dict]) -> None:
    print("\n-- multiplicateur m(h) qui donne 95 % sur cet échantillon")
    found = {}
    for h in range(1, 31):
        for m in np.arange(0.5, 2.51, 0.02):
            cov = np.mean([lo <= r["actual"][h - 1] <= hi for r in rows for lo, hi in [band(r, h, m)]])
            if cov >= LEVEL:
                found[h] = round(float(m), 2)
                break
    print(found)
    hs = np.array(sorted(found))
    a, b = np.polyfit(np.log(hs), [found[h] for h in hs], 1)
    print(f"ajustement m(h) = {b:.3f} + {a:.3f}·ln(h)")


if __name__ == "__main__":
    data = sys.argv[sys.argv.index("--data") + 1] if "--data" in sys.argv else "binance_daily.json"
    rows = load(sys.argv[1], data)
    kappa_table(rows)
    multipliers(rows)
