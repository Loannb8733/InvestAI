"""Synthèse d'un ou plusieurs backtests, en tableaux Markdown côte à côte.

Usage :
    python analyze.py avant=chemin/results.jsonl apres=chemin/results.jsonl
"""

import json
import sys
from collections import defaultdict

import numpy as np

HORIZONS = [1, 7, 30]
MODELS = ["Prophet", "ARIMA", "XGBoost", "EMA", "Linear", "MeanReversion", "Naive"]


def ape(pred: float, act: float) -> float:
    return abs(pred - act) / act * 100


def metrics(path: str) -> dict:
    res = [json.loads(line) for line in open(path) if line.strip()]
    out: dict = {"n": len(res), "secs": float(np.mean([r["secs"] for r in res]))}
    for h in HORIZONS:
        d: dict[str, list] = defaultdict(list)
        for r in res:
            p0, a = r["p0"], r["actual"][h - 1]
            e = r["ens"][h - 1]
            d["naive"].append(ape(p0, a))
            d["ens"].append(ape(e, a))
            d["beats"].append(ape(e, a) < ape(p0, a))
            d["dir"].append((e > p0) == (a > p0))
            d["cover"].append(r["low"][h - 1] <= a <= r["high"][h - 1])
            d["width"].append((r["high"][h - 1] - r["low"][h - 1]) / p0 * 100)
            for m, s in r["single"].items():
                if isinstance(s, list):
                    d[m].append(ape(s[h - 1], a))
        out[h] = d
    return out


def fmt(values: list, kind: str) -> str:
    if not values:
        return "—"
    if kind == "pct_mean":
        return f"{np.mean(values):.2f} %"
    if kind == "pct_median":
        return f"{np.median(values):.2f} %"
    if kind == "pct_max":
        return f"{np.max(values):.0f} %"
    return f"{np.mean(values) * 100:.0f} %"


ROWS = [
    ("MAPE naïf (prix constant)", "naive", "pct_mean"),
    ("MAPE ensemble", "ens", "pct_mean"),
    ("Erreur médiane ensemble", "ens", "pct_median"),
    ("Ensemble meilleur que le naïf", "beats", "share"),
    ("Direction juste", "dir", "share"),
    ("Couverture de l'intervalle « 95 % »", "cover", "share"),
    ("Largeur de l'intervalle (% du prix)", "width", "pct_mean"),
]


def main(args: list[str]) -> None:
    runs = {name: metrics(path) for name, path in (a.split("=", 1) for a in args)}
    names = list(runs)
    head = "| | " + " | ".join(names) + " |\n|---|" + "---:|" * len(names)
    print("Origines : " + ", ".join(f"{n} {runs[n]['n']}" for n in names))
    print("Temps moyen d'un ensemble : " + ", ".join(f"{n} {runs[n]['secs']:.1f} s" for n in names))
    for h in HORIZONS:
        print(f"\n#### Horizon {h} j\n\n{head}")
        for label, key, kind in ROWS:
            print(f"| {label} | " + " | ".join(fmt(runs[n][h][key], kind) for n in names) + " |")
        for m in MODELS:
            print(f"| {m} : MAPE | " + " | ".join(fmt(runs[n][h][m], "pct_mean") for n in names) + " |")
            print(f"| {m} : erreur médiane | " + " | ".join(fmt(runs[n][h][m], "pct_median") for n in names) + " |")
            print(f"| {m} : erreur max | " + " | ".join(fmt(runs[n][h][m], "pct_max") for n in names) + " |")


if __name__ == "__main__":
    main(sys.argv[1:])
