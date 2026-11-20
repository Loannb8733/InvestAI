"""Recombine hors ligne les prévisions par modèle d'un backtest, pour choisir une méthode sur la validation.

Chaque méthode ne dépend que de ce qui est connu à la date de la prévision : les trajectoires des modèles et
l'historique des cours. Elle est donc transposable telle quelle dans ``app.ml.forecasting``.

    prévision(h) = p0 · exp(λ · c(h) − κ · v(h))

c(h) : rendement log de la combinaison (ensemble actuel, médiane ou moyenne des modèles) ; λ : rétrécissement
vers la prévision naïve (λ = 0) ; v(h) : variance des rendements log sur h jours, estimée sur l'année passée ;
κ = 1 donne la prévision qui minimise l'erreur relative attendue (MAPE) quand les rendements sont log-normaux.

Usage :
    python combine.py grille <validation.jsonl>
    python combine.py evaluer <results.jsonl> <combo> <lambda> <kappa> <z> [--data fichier.json]
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
HORIZONS = (1, 7, 30)
HISTORY = 365
COMBOS = ("ens", "median", "mean")
LAMBDAS = (0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0)
KAPPAS = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5)
ZS = (1.6, 1.8, 1.96, 2.1, 2.3, 2.5)


def _series(data_file: str) -> dict[str, dict[str, float]]:
    raw = json.loads((HERE / "data" / data_file).read_text())
    return {s: dict(zip(v["dates"], v["close"], strict=True)) for s, v in raw.items()}


def _history(closes: dict[str, float], origin: str) -> np.ndarray:
    dates = sorted(d for d in closes if d <= origin)[-HISTORY:]
    return np.log(np.array([closes[d] for d in dates]))


def load(path: str, data_file: str) -> list[dict]:
    series = _series(data_file)
    rows = [json.loads(line) for line in open(path) if line.strip()]
    for r in rows:
        logp = _history(series[r["symbol"]], r["origin"])
        daily = np.diff(logp)
        r["rets"] = {h: logp[h:] - logp[:-h] for h in range(1, 31)}
        r["var_h"] = {h: float(np.var(r["rets"][h])) for h in range(1, 31)}
        r["sd_d"] = float(np.std(daily))
        p0 = r["p0"]
        models = [np.log(np.array(s) / p0) for s in r["single"].values() if isinstance(s, list) and min(s) > 0]
        stack = np.vstack(models)
        r["c"] = {
            "ens": np.log(np.array(r["ens"]) / p0),
            "median": np.median(stack, axis=0),
            "mean": np.mean(stack, axis=0),
        }
    return rows


def forecast(r: dict, h: int, combo: str, lam: float, kappa: float) -> float:
    return r["p0"] * float(np.exp(lam * r["c"][combo][h - 1] - kappa * r["var_h"][h]))


def interval(r: dict, h: int, z: float) -> tuple[float, float]:
    sd = float(np.sqrt(r["var_h"][h]))
    return r["p0"] * float(np.exp(-z * sd)), r["p0"] * float(np.exp(z * sd))


def ape(pred: float, act: float) -> float:
    return abs(pred - act) / act * 100


def scores(rows: list[dict], combo: str, lam: float, kappa: float) -> dict:
    by: dict = defaultdict(list)
    for r in rows:
        for h in HORIZONS:
            act = r["actual"][h - 1]
            e = ape(forecast(r, h, combo, lam, kappa), act)
            n = ape(r["p0"], act)
            by[("all", h)].append((e, n))
            by[(r["symbol"], h)].append((e, n))
    return {k: (float(np.mean([e for e, _ in v])), float(np.mean([n for _, n in v]))) for k, v in by.items()}


def grid(path: str, data_file: str) -> None:
    rows = load(path, data_file)
    results = []
    for combo in COMBOS:
        for lam in LAMBDAS:
            for kappa in KAPPAS:
                s = scores(rows, combo, lam, kappa)
                ratio = np.mean([s[("all", h)][0] / s[("all", h)][1] for h in HORIZONS])
                worst = max(e / n for (sym, _), (e, n) in s.items() if sym != "all")
                results.append((ratio, worst, combo, lam, kappa, [s[("all", h)][0] for h in HORIZONS]))
    results.sort()
    naive = scores(rows, "ens", 0.0, 0.0)
    print("naïf MAPE 1/7/30 :", [round(naive[("all", h)][1], 3) for h in HORIZONS], f"({len(rows)} prévisions)")
    print("ratio_moyen  pire_actif×horizon  combo  λ  κ  MAPE 1/7/30")
    for ratio, worst, combo, lam, kappa, m in results[:15]:
        print(f"{ratio:.4f}  {worst:.4f}  {combo:6} {lam:.1f} {kappa:.2f}  {[round(x, 3) for x in m]}")
    floor = [x for x in results if x[1] <= 1.0]
    print(
        "meilleure méthode jamais pire que le naïf sur chaque actif × horizon :", floor[0][2:5] if floor else "aucune"
    )
    for z in ZS:
        cov = {
            h: np.mean([interval(r, h, z)[0] <= r["actual"][h - 1] <= interval(r, h, z)[1] for r in rows])
            for h in HORIZONS
        }
        wid = {
            h: np.mean([(interval(r, h, z)[1] - interval(r, h, z)[0]) / r["p0"] * 100 for r in rows]) for h in HORIZONS
        }
        print(
            f"z={z}: couverture {[f'{cov[h]:.1%}' for h in HORIZONS]} largeur {[f'{wid[h]:.1f} %' for h in HORIZONS]}"
        )


if __name__ == "__main__":
    cmd = sys.argv[1]
    data = sys.argv[sys.argv.index("--data") + 1] if "--data" in sys.argv else "binance_daily.json"
    if cmd == "grille":
        grid(sys.argv[2], data)
