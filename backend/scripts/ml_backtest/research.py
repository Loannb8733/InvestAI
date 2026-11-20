"""Recherche systématique de signaux qui battent la prévision naïve, en walk-forward quotidien sur la validation.

Une origine par jour et par actif (6 cryptos de développement), de janvier 2022 jusqu'à la veille du banc
historique : aucune cible de validation ne déborde sur le banc. Les modèles sont réentraînés tous les 30 jours sur
les seules cibles déjà réalisées à la date de réentraînement. Chaque méthode prévoit un rendement log g sur h
jours ; la prévision est p0 · exp(g). Le gain est jugé par un test de Diebold-Mariano sur l'écart d'erreur
relative avec le naïf, écart-type de Newey-West (h − 1 retards) pour les horizons qui se chevauchent.

    python research.py [--horizons 1,7,30]
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import HuberRegressor, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
DEV = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "ADAUSDT")
VALIDATION_START = "2022-01-01"
BENCH_START = "2024-11-22"
REFIT_DAYS = 30
FEATURES = [
    "lr1",
    "lr3",
    "lr7",
    "lr14",
    "lr30",
    "lr90",
    "vol7",
    "vol30",
    "volratio",
    "vz",
    "btc_lr1",
    "btc_lr7",
    "btc_lr30",
    "dow_sin",
    "dow_cos",
    "hi30",
    "lo30",
]


def frame(symbol: str, raw: dict, btc: pd.Series) -> pd.DataFrame:
    s = raw[symbol]
    df = pd.DataFrame({"close": s["close"], "qvol": s["quote_volume"]}, index=pd.to_datetime(s["dates"]))
    lp = np.log(df["close"])
    d1 = lp.diff()
    for k in (1, 3, 7, 14, 30, 90):
        df[f"lr{k}"] = lp - lp.shift(k)
    df["vol7"], df["vol30"], df["vol365"] = d1.rolling(7).std(), d1.rolling(30).std(), d1.rolling(365).std()
    df["volratio"] = df["vol7"] / df["vol30"]
    df["vz"] = np.log(df["qvol"]) - np.log(df["qvol"]).rolling(30).mean()
    blp = np.log(btc.reindex(df.index))
    for k in (1, 7, 30):
        df[f"btc_lr{k}"] = blp - blp.shift(k)
    dow = df.index.dayofweek
    df["dow_sin"], df["dow_cos"] = np.sin(2 * np.pi * dow / 7), np.cos(2 * np.pi * dow / 7)
    df["hi30"] = lp - lp.rolling(30).max()
    df["lo30"] = lp - lp.rolling(30).min()
    for h in (1, 7, 30):
        df[f"y{h}"] = lp.shift(-h) - lp
    df["symbol"] = symbol
    return df.dropna(subset=["lr90", "vol30"])


def ape(g: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.abs(np.exp(g - y) - 1) * 100


def dm(loss_a: np.ndarray, loss_b: np.ndarray, lag: int) -> float:
    d = loss_a - loss_b
    n = len(d)
    dc = d - d.mean()
    var = dc @ dc / n
    for k in range(1, lag + 1):
        var += 2 * (1 - k / (lag + 1)) * (dc[k:] @ dc[:-k]) / n
    return float(d.mean() / np.sqrt(var / n))


def models() -> dict:
    return {
        "ridge": lambda: make_pipeline(StandardScaler(), Ridge(alpha=100.0)),
        "huber": lambda: make_pipeline(StandardScaler(), HuberRegressor(epsilon=1.35, alpha=1.0, max_iter=500)),
        "hgb_l1": lambda: HistGradientBoostingRegressor(
            loss="absolute_error", max_iter=150, learning_rate=0.03, max_leaf_nodes=15, min_samples_leaf=200
        ),
    }


def walk_forward(data: pd.DataFrame, h: int) -> pd.DataFrame:
    target = f"y{h}"
    rows = data.dropna(subset=[*FEATURES, target])
    val = (
        rows[(rows.index >= VALIDATION_START) & (rows.index + pd.Timedelta(days=h) < BENCH_START)]
        .dropna(subset=["vol365"])
        .copy()
    )
    refits = pd.date_range(VALIDATION_START, val.index.max(), freq=f"{REFIT_DAYS}D")
    for name in models():
        val[name] = np.nan
    for start in refits:
        stop = start + pd.Timedelta(days=REFIT_DAYS)
        train = rows[rows.index + pd.Timedelta(days=h) <= start]
        block = (val.index >= start) & (val.index < stop)
        if not block.any():
            continue
        for name, make in models().items():
            model = make().fit(train[FEATURES].to_numpy(), train[target].to_numpy())
            val.loc[block, name] = model.predict(val.loc[block, FEATURES].to_numpy())
    val["naive"] = 0.0
    for kappa in (0.25, 0.5, 1.0):
        val[f"shift{kappa}"] = -kappa * val["vol365"] ** 2 * h
    return val


def single_signals(val: pd.DataFrame, h: int) -> None:
    target = f"y{h}"
    print(f"   corrélations signal → rendement futur {h} j (validation, n={len(val)}) :")
    corr = {f: float(np.corrcoef(val[f], val[target])[0, 1]) for f in FEATURES}
    for f, c in sorted(corr.items(), key=lambda kv: -abs(kv[1]))[:8]:
        print(f"     {f:9} {c:+.3f}")


def report(val: pd.DataFrame, h: int) -> None:
    y = val[f"y{h}"].to_numpy()
    base = ape(val["naive"].to_numpy(), y)
    print(f"\n== horizon {h} j : {len(val)} prévisions, MAPE naïf {base.mean():.3f} %")
    methods = [c for c in val.columns if c in models() or c.startswith("shift")]
    for m in methods:
        loss = ape(val[m].to_numpy(), y)
        per = val.assign(_l=loss, _b=base).groupby("symbol")[["_l", "_b"]].mean()
        worst = float((per["_l"] / per["_b"]).max())
        print(
            f"   {m:10} MAPE {loss.mean():.3f} %  ratio {loss.mean() / base.mean():.4f}  DM {dm(loss, base, h - 1):+.2f}  pire actif {worst:.4f}"
        )
    single_signals(val, h)


def main() -> None:
    horizons = (
        [int(x) for x in sys.argv[sys.argv.index("--horizons") + 1].split(",")]
        if "--horizons" in sys.argv
        else [1, 7, 30]
    )
    raw = json.loads((HERE / "data" / "binance_daily.json").read_text())
    btc = pd.Series(raw["BTCUSDT"]["close"], index=pd.to_datetime(raw["BTCUSDT"]["dates"]))
    data = pd.concat([frame(s, raw, btc) for s in DEV]).sort_index()
    for h in horizons:
        report(walk_forward(data, h), h)


if __name__ == "__main__":
    main()
