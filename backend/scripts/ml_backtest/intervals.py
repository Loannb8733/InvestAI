"""Méthodes d'intervalle calibrées sur la validation : m(h) = a + b·ln h ajusté pour couvrir 95 % à chaque h.

python intervals.py <validation.jsonl> <controle.jsonl>
"""

import sys

import numpy as np
from combine import load

LEVEL = 0.95


def ewma_sd(r: dict, lam: float = 0.94) -> float:
    rets = r["rets"][1]
    var = float(np.var(rets[:30]))
    for x in rets[30:]:
        var = lam * var + (1 - lam) * x * x
    return float(np.sqrt(var))


def raw(r: dict, h: int, method: str) -> tuple[float, float]:
    if method == "quantiles":
        lo, hi = np.quantile(r["rets"][h], [(1 - LEVEL) / 2, 1 - (1 - LEVEL) / 2])
        return float(lo), float(hi)
    sd = (r["sd_d"] if method == "vol" else r["ewma"]) * np.sqrt(h) * 1.96
    return -sd, sd


def coverage(rows: list[dict], h: int, method: str, m: float) -> tuple[float, float]:
    hits, widths = [], []
    for r in rows:
        lo, hi = raw(r, h, method)
        low, high = r["p0"] * np.exp(m * lo), r["p0"] * np.exp(m * hi)
        hits.append(low <= r["actual"][h - 1] <= high)
        widths.append((high - low) / r["p0"] * 100)
    return float(np.mean(hits)), float(np.mean(widths))


def fit(rows: list[dict], method: str) -> tuple[float, float]:
    found = {}
    for h in range(1, 31):
        for m in np.arange(0.3, 3.01, 0.01):
            if coverage(rows, h, method, m)[0] >= LEVEL:
                found[h] = m
                break
    hs = np.array(sorted(found))
    slope, intercept = np.polyfit(np.log(hs), [found[h] for h in hs], 1)
    return float(intercept), float(slope)


if __name__ == "__main__":
    val = load(sys.argv[1], "binance_daily.json")
    ctrl = load(sys.argv[2], "binance_daily.json")
    for r in val + ctrl:
        r["ewma"] = ewma_sd(r)
    for method in ("quantiles", "vol", "ewma"):
        a, b = fit(val, method)
        print(f"\n{method} : m(h) = {a:.3f} + {b:.3f}·ln h")
        for name, rows in (("validation", val), ("banc", ctrl)):
            cells = []
            for h in (1, 7, 30):
                cov, wid = coverage(rows, h, method, a + b * np.log(h))
                cells.append(f"{h} j {cov:.0%} / {wid:.1f} %")
            print(f"  {name:10} " + "   ".join(cells))
