"""Correction MAPE p0 · exp(−κ(h) · σ_w² · h) et intervalles ± 1,96 · m(h) · σ_w · √h, en origines quotidiennes.

Règle de choix, fixée avant de regarder le banc ou un test : pour chaque horizon, le κ qui minimise le MAPE de
validation parmi ceux qui sont meilleurs que le naïf sur chaque actif avec un Diebold-Mariano < −2 ; sinon 0.
m(h) = a + b · ln h ajusté sur la validation pour couvrir 95 % à chaque horizon de 1 à 30 jours.

    python research_shift.py valider
    python research_shift.py controler <fichier de données> <début> <fin> <window> <k1> <k7> <k30> <a> <b>
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from research import BENCH_START, DEV, VALIDATION_START, ape, dm

HERE = Path(__file__).resolve().parent
WINDOWS = (30, 90, 180, 365)
KAPPAS = np.round(np.arange(0.1, 1.51, 0.1), 2)
HORIZONS = range(1, 31)
REPORTED = (1, 7, 30)


def frames(data_file: str, symbols: list[str]) -> pd.DataFrame:
    raw = json.loads((HERE / "data" / data_file).read_text())
    out = []
    for s in symbols:
        lp = np.log(pd.Series(raw[s]["close"], index=pd.to_datetime(raw[s]["dates"])))
        d1 = lp.diff()
        df = pd.DataFrame({"symbol": s}, index=lp.index)
        for w in WINDOWS:
            df[f"sd{w}"] = d1.rolling(w).std()
        for h in HORIZONS:
            df[f"y{h}"] = lp.shift(-h) - lp
        out.append(df.dropna(subset=["sd365"]))
    return pd.concat(out).sort_index()


def window(df: pd.DataFrame, start: str, stop: str, h: int) -> pd.DataFrame:
    return df[(df.index >= start) & (df.index + pd.Timedelta(days=h) < stop)].dropna(subset=[f"y{h}"])


def shift_stats(df: pd.DataFrame, h: int, w: int, kappa: float) -> tuple[float, float, float, float]:
    y = df[f"y{h}"].to_numpy()
    base = ape(np.zeros_like(y), y)
    loss = ape(-kappa * df[f"sd{w}"].to_numpy() ** 2 * h, y)
    per = df.assign(_l=loss, _b=base).groupby("symbol")[["_l", "_b"]].mean()
    return float(loss.mean()), float(base.mean()), float((per["_l"] / per["_b"]).max()), dm(loss, base, h - 1)


def choose(df: pd.DataFrame, w: int) -> dict[int, float]:
    chosen = {}
    for h in REPORTED:
        val = window(df, VALIDATION_START, BENCH_START, h)
        ok = [
            (shift_stats(val, h, w, k)[0], k) for k in KAPPAS if (s := shift_stats(val, h, w, k))[2] < 1 and s[3] < -2
        ]
        chosen[h] = min(ok)[1] if ok else 0.0
    return chosen


def coverage(df: pd.DataFrame, h: int, w: int, m: float) -> tuple[float, float]:
    y = df[f"y{h}"].to_numpy()
    spread = 1.96 * m * df[f"sd{w}"].to_numpy() * np.sqrt(h)
    return float(np.mean(np.abs(y) <= spread)), float(np.mean(np.exp(spread) - np.exp(-spread)) * 100)


def fit_scale(df: pd.DataFrame, w: int) -> tuple[float, float]:
    found = {}
    for h in HORIZONS:
        val = window(df, VALIDATION_START, BENCH_START, h)
        spread = 1.96 * val[f"sd{w}"].to_numpy() * np.sqrt(h)
        found[h] = float(np.quantile(np.abs(val[f"y{h}"].to_numpy()) / spread, 0.95))
    slope, intercept = np.polyfit(np.log(list(found)), list(found.values()), 1)
    return float(intercept), float(slope)


def validate() -> None:
    df = frames("binance_daily.json", list(DEV))
    for w in WINDOWS:
        print(f"\n== volatilité sur {w} j")
        for h in REPORTED:
            val = window(df, VALIDATION_START, BENCH_START, h)
            cells = [
                f"κ={k:.1f}: {(s := shift_stats(val, h, w, k))[0]:.3f} ({s[2]:.4f}, DM {s[3]:+.1f})"
                for k in (0.3, 0.5, 0.7, 1.0)
            ]
            print(f"   {h:2} j naïf {shift_stats(val, h, w, 0.1)[1]:.3f} | " + " | ".join(cells))
        chosen = choose(df, w)
        a, b = fit_scale(df, w)
        widths = []
        for h in REPORTED:
            cov, wid = coverage(window(df, VALIDATION_START, BENCH_START, h), h, w, a + b * np.log(h))
            widths.append(f"{h} j {cov:.1%} / {wid:.1f} %")
        print(f"   κ choisis {chosen}  m(h) = {a:.3f} + {b:.3f}·ln h  intervalles {'  '.join(widths)}")


def control(data_file: str, start: str, stop: str, w: int, kappas: dict[int, float], a: float, b: float) -> None:
    raw = json.loads((HERE / "data" / data_file).read_text())
    df = frames(data_file, sorted(raw))
    print(f"{data_file} {start} → {stop}, volatilité {w} j, κ {kappas}, m(h) = {a} + {b}·ln h")
    print("| Horizon | Prévisions | MAPE naïf | MAPE corrigé | Gain | DM | Pire actif / naïf | Couverture | Largeur |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    per_asset = {}
    for h in REPORTED:
        sub = window(df, start, stop, h)
        loss, base, worst, stat = shift_stats(sub, h, w, kappas[h])
        cov, wid = coverage(sub, h, w, a + b * np.log(h))
        print(
            f"| {h} j | {len(sub)} | {base:.2f} % | {loss:.2f} % | {(loss / base - 1) * 100:+.1f} % | {stat:+.1f} | {worst:.4f} | {cov:.1%} | {wid:.1f} % |"
        )
        y = sub[f"y{h}"].to_numpy()
        sub = sub.assign(_b=ape(np.zeros_like(y), y), _l=ape(-kappas[h] * sub[f"sd{w}"].to_numpy() ** 2 * h, y))
        per_asset[h] = sub.groupby("symbol")[["_b", "_l"]].mean()
    print("\n| Actif | " + " | ".join(f"{h} j naïf → corrigé" for h in REPORTED) + " |")
    print("|---|" + "---:|" * len(REPORTED))
    for s in per_asset[1].index:
        print(
            f"| {s.replace('USDT', '')} | "
            + " | ".join(f"{per_asset[h].loc[s, '_b']:.2f} → {per_asset[h].loc[s, '_l']:.2f} %" for h in REPORTED)
            + " |"
        )


if __name__ == "__main__":
    if sys.argv[1] == "valider":
        validate()
    else:
        _, _, data, start, stop, w, k1, k7, k30, a, b = sys.argv
        control(data, start, stop, int(w), {1: float(k1), 7: float(k7), 30: float(k30)}, float(a), float(b))
