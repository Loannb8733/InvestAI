"""Backtest walk-forward du PriceForecaster d'InvestAI sur les clôtures quotidiennes publiques de Binance.

Aucun accès à la base ni à Redis : le script importe seulement ``app.ml``. Les cours sont téléchargés une fois
puis figés dans ``data/binance_daily.json`` (jusqu'à ``BT_END``), pour que deux exécutions comparent les mêmes
séries.

Usage :
    python backtest.py <dossier_de_sortie>

Variables :
    BT_BACKEND   dossier ``backend`` dont on évalue le code (par défaut celui de ce dépôt) ;
    BT_SYMBOLS   paires Binance, séparées par des virgules ;
    BT_STEP      jours entre deux origines ;
    BT_ORIGINS   nombre d'origines par paire ;
    BT_WORKERS   processus en parallèle ;
    BT_END       dernier jour des données figées (AAAA-MM-JJ).
"""

import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "backtest_only_dummy_secret_key_1234567890")
os.environ.setdefault("FERNET_KEY", "icQAqvAxUzGIr5HCiFPkDICQtKw_tIwRDbCnZW0HW6M=")
os.environ.setdefault("POSTGRES_USER", "backtest")
os.environ.setdefault("POSTGRES_PASSWORD", "backtest")
os.environ["REDIS_URL"] = "redis://localhost:6399/0"
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_v] = "1"

HERE = Path(__file__).resolve().parent
BACKEND = Path(os.environ.get("BT_BACKEND", HERE.parents[1])).expanduser().resolve()
DATA = HERE / "data" / "binance_daily.json"
SYMBOLS = os.environ.get("BT_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT,ADAUSDT").split(",")
END = os.environ.get("BT_END", "2026-11-15")
HISTORY = 365
HORIZON = 30
STEP = int(os.environ.get("BT_STEP", "21"))
N_ORIGINS = int(os.environ.get("BT_ORIGINS", "34"))
WORKERS = int(os.environ.get("BT_WORKERS", "8"))
MODELS = ["Prophet", "ARIMA", "XGBoost", "EMA", "Linear", "MeanReversion", "Naive"]


def _klines(symbol: str) -> dict[str, list]:
    rows: list[list] = []
    start = int(datetime(2021, 1, 1, tzinfo=UTC).timestamp() * 1000)
    end = int(datetime.fromisoformat(END).replace(tzinfo=UTC).timestamp() * 1000)
    while start <= end:
        url = (
            "https://data-api.binance.vision/api/v3/klines"
            f"?symbol={symbol}&interval=1d&limit=1000&startTime={start}&endTime={end}"
        )
        with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310
            batch = json.loads(r.read())
        if not batch:
            break
        rows += batch
        if len(batch) < 1000:
            break
        start = batch[-1][0] + 86_400_000
    return {
        "dates": [datetime.fromtimestamp(k[0] / 1000, tz=UTC).date().isoformat() for k in rows],
        "close": [float(k[4]) for k in rows],
        "quote_volume": [float(k[7]) for k in rows],
    }


def load_data() -> dict[str, dict[str, list]]:
    """Séries figées ; téléchargées et enregistrées au premier lancement ou pour un symbole nouveau."""
    data: dict[str, dict[str, list]] = json.loads(DATA.read_text()) if DATA.exists() else {}
    missing = [s for s in SYMBOLS if s not in data]
    if missing:
        for s in missing:
            data[s] = _klines(s)
        DATA.parent.mkdir(parents=True, exist_ok=True)
        DATA.write_text(json.dumps(data, separators=(",", ":")))
    return {s: data[s] for s in SYMBOLS}


def one_origin(args: tuple) -> dict:
    symbol, i, dates, prices, vols, btc = args
    sys.path.insert(0, str(BACKEND))
    import logging

    logging.disable(logging.WARNING)
    from app.ml.forecasting.ensemble import PriceForecaster

    lo = i - HISTORY
    p, d, v = prices[lo:i], dates[lo:i], vols[lo:i]
    b = btc[lo:i] if btc else None
    f = PriceForecaster()
    t0 = time.time()
    res = f.ensemble_forecast(p, d, HORIZON, volumes=v, btc_prices=b)
    out = {
        "symbol": symbol,
        "origin": d[-1].date().isoformat(),
        "p0": p[-1],
        "actual": prices[i : i + HORIZON],
        "ens": res.prices,
        "low": res.confidence_low,
        "high": res.confidence_high,
        "trend": res.trend,
        "model_used": res.model_used,
        "secs": round(time.time() - t0, 1),
        "single": {},
        "single_secs": {},
    }
    for m in MODELS:
        try:
            extra = {"volumes": v, "btc_prices": b} if m == "XGBoost" else {}
            t1 = time.time()
            out["single"][m] = f.run_model(m, p, d, HORIZON, **extra).prices
            out["single_secs"][m] = round(time.time() - t1, 1)
        except Exception as e:  # noqa: BLE001
            out["single"][m] = f"error: {e}"
    return out


def main(out_dir: str) -> None:
    raw = load_data()
    data = {s: ([datetime.fromisoformat(x) for x in r["dates"]], r["close"], r["quote_volume"]) for s, r in raw.items()}
    btc_by_date = dict(zip(data["BTCUSDT"][0], data["BTCUSDT"][1], strict=True))
    jobs = []
    for s, (d, p, v) in data.items():
        btc = None if s == "BTCUSDT" else [btc_by_date.get(x) for x in d]
        last = len(p) - HORIZON
        for k in range(N_ORIGINS):
            i = last - k * STEP
            if i - HISTORY < 0:
                break
            if btc and any(x is None for x in btc[i - HISTORY : i]):
                continue
            jobs.append((s, i, d, p, v, btc))
    print(f"backend: {BACKEND}\n{len(jobs)} origines", flush=True)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "results.jsonl")
    with open(path, "w") as fh, ProcessPoolExecutor(max_workers=WORKERS) as ex:
        for n, r in enumerate(ex.map(one_origin, jobs), 1):
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            print(f"{n}/{len(jobs)} {r['symbol']} {r['origin']} ens={r['secs']}s", flush=True)
    print("termine", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
