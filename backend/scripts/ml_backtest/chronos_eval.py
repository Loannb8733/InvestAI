"""Chronos-Bolt sans réentraînement, en origines quotidiennes, contre le naïf et la correction MAPE retenue.

À lancer avec l'environnement ``~/envs/chronos`` (torch CPU, chronos-forecasting). Contexte : les 512 derniers
cours. Deux prévisions : la médiane de Chronos, et le point qui minimise l'erreur relative attendue sous ses
quantiles 10 % à 90 %.

    python chronos_eval.py <fichier de données> <début> <fin> [modèle]
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from chronos import BaseChronosPipeline

HERE = Path(__file__).resolve().parent
CONTEXT = 512
HORIZONS = (1, 7, 30)
LEVELS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
KAPPA = {1: 0.6, 7: 0.9, 30: 0.9}
VOL_WINDOW = 365
BATCH = 128


def dm(loss_a: np.ndarray, loss_b: np.ndarray, lag: int) -> float:
    d = loss_a - loss_b
    n, dc = len(d), d - d.mean()
    var = dc @ dc / n
    for k in range(1, lag + 1):
        var += 2 * (1 - k / (lag + 1)) * (dc[k:] @ dc[:-k]) / n
    return float(d.mean() / np.sqrt(var / n))


def mape_point(quantiles: np.ndarray) -> np.ndarray:
    candidates = quantiles[..., None, :]
    grid = quantiles[..., :, None]
    cost = np.abs(candidates - grid) / grid
    best = cost.mean(axis=-2).argmin(axis=-1)
    return np.take_along_axis(quantiles, best[..., None], axis=-1)[..., 0]


def main(data_file: str, start: str, stop: str, model: str) -> None:
    raw = json.loads((HERE / "data" / data_file).read_text())
    pipe = BaseChronosPipeline.from_pretrained(model, device_map="cpu", torch_dtype=torch.float32)
    rows: dict = {h: [] for h in HORIZONS}
    t0 = time.time()
    for symbol, series in sorted(raw.items()):
        dates, closes = series["dates"], np.asarray(series["close"], dtype=float)
        origins = [i for i, d in enumerate(dates) if start <= d < stop and i >= max(CONTEXT, VOL_WINDOW + 1)]
        for b in range(0, len(origins), BATCH):
            chunk = origins[b : b + BATCH]
            ctx = [torch.tensor(closes[i - CONTEXT + 1 : i + 1]) for i in chunk]
            q, _ = pipe.predict_quantiles(ctx, prediction_length=30, quantile_levels=LEVELS)
            q = q.numpy()
            median, best = q[..., LEVELS.index(0.5)], mape_point(q)
            for j, i in enumerate(chunk):
                p0 = closes[i]
                sigma = np.std(np.diff(np.log(closes[i - VOL_WINDOW : i + 1])), ddof=1)
                for h in HORIZONS:
                    if i + h >= len(closes) or dates[i + h] >= stop:
                        continue
                    act = closes[i + h]
                    shift = p0 * np.exp(-KAPPA[h] * sigma**2 * h)
                    rows[h].append(
                        (symbol, *(abs(f - act) / act * 100 for f in (p0, shift, median[j, h - 1], best[j, h - 1])))
                    )
        print(f"{symbol} fait ({time.time() - t0:.0f} s)", flush=True)
    print(f"\n{model} sur {data_file} {start} → {stop}")
    print(
        "| Horizon | n | Naïf | Correction retenue | Chronos médiane | Chronos point MAPE | DM médiane/naïf | DM point MAPE/correction | Pire actif point MAPE/naïf |"
    )
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for h in HORIZONS:
        sym = np.array([r[0] for r in rows[h]])
        naive, shift, med, best = (np.array([r[k] for r in rows[h]]) for k in (1, 2, 3, 4))
        worst = max(best[sym == s].mean() / naive[sym == s].mean() for s in set(sym))
        print(
            f"| {h} j | {len(naive)} | {naive.mean():.3f} % | {shift.mean():.3f} % | {med.mean():.3f} % | {best.mean():.3f} % "
            f"| {dm(med, naive, h - 1):+.1f} | {dm(best, shift, h - 1):+.1f} | {worst:.4f} |"
        )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "amazon/chronos-bolt-small")
