"""Évalue le code de production ``app.ml.forecasting.floor`` en origines quotidiennes sur un jeu figé.

Pour chaque actif et chaque jour de la période, l'historique jusqu'à ce jour est passé à ``floor.anchored`` :
MAPE servi contre naïf à 1, 7 et 30 jours, test de Diebold-Mariano, détail par actif, couverture et largeur.

    python evaluate_floor.py <fichier de données> <début> <fin>
"""

import json
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
os.environ.setdefault("SECRET_KEY", "backtest_only_dummy_secret_key_1234567890")
os.environ.setdefault("FERNET_KEY", "icQAqvAxUzGIr5HCiFPkDICQtKw_tIwRDbCnZW0HW6M=")

from research import dm  # noqa: E402

from app.ml.forecasting import floor  # noqa: E402

HORIZONS = (1, 7, 30)


def evaluate(data_file: str, start: str, stop: str) -> None:
    raw = json.loads((HERE / "data" / data_file).read_text())
    rows: dict = {h: [] for h in HORIZONS}
    for symbol, series in sorted(raw.items()):
        dates, closes = series["dates"], series["close"]
        for i, day in enumerate(dates):
            if not (start <= day < stop) or i < floor.VOL_WINDOW + 1:
                continue
            point, low, high = floor.anchored(closes[: i + 1], 30)
            for h in HORIZONS:
                if i + h >= len(closes) or dates[i + h] >= stop:
                    continue
                act, p0 = closes[i + h], closes[i]
                rows[h].append(
                    (
                        symbol,
                        abs(p0 - act) / act * 100,
                        abs(point[h - 1] - act) / act * 100,
                        low[h - 1] <= act <= high[h - 1],
                        (high[h - 1] - low[h - 1]) / p0 * 100,
                    )
                )
    print(f"{data_file} {start} → {stop} (code de production)")
    print("| Horizon | Prévisions | MAPE naïf | MAPE servi | Gain | DM | Actifs ≤ naïf | Couverture | Largeur |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    per: dict = {}
    for h in HORIZONS:
        sym = np.array([r[0] for r in rows[h]])
        base, served = np.array([r[1] for r in rows[h]]), np.array([r[2] for r in rows[h]])
        per[h] = {s: (base[sym == s].mean(), served[sym == s].mean()) for s in sorted(set(sym))}
        ok = sum(v[1] <= v[0] for v in per[h].values())
        print(
            f"| {h} j | {len(base)} | {base.mean():.2f} % | {served.mean():.2f} % | {(served.mean() / base.mean() - 1) * 100:+.1f} % "
            f"| {dm(served, base, h - 1):+.1f} | {ok}/{len(per[h])} | {np.mean([r[3] for r in rows[h]]):.1%} | {np.mean([r[4] for r in rows[h]]):.1f} % |"
        )
    print("\n| Actif | " + " | ".join(f"{h} j naïf → servi" for h in HORIZONS) + " |")
    print("|---|" + "---:|" * len(HORIZONS))
    for s in per[1]:
        print(
            f"| {s.replace('USDT', '')} | "
            + " | ".join(f"{per[h][s][0]:.2f} → {per[h][s][1]:.2f} %" for h in HORIZONS)
            + " |"
        )


if __name__ == "__main__":
    evaluate(sys.argv[1], sys.argv[2], sys.argv[3])
