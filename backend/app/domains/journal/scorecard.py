import bisect
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from app.domains.journal.models import Note
from app.domains.journal.repository import SCORED_SENTIMENTS, AssetRef, PriceSeries
from app.domains.journal.schemas import (
    ScorecardEntry,
    ScorecardResponse,
    ScorecardSentimentStats,
    ScorecardSummary,
    Verdict,
)

DIRECTIONAL_THRESHOLD_PCT = 2.0
NEUTRAL_BAND_PCT = 5.0
PRICE_TOLERANCE_DAYS = 3
HORIZONS = (30, 90)


def nearest_price(series: PriceSeries, target: date) -> Decimal | None:
    index = bisect.bisect_left(series.dates, target)
    best: Decimal | None = None
    best_delta: int | None = None
    for candidate in (index - 1, index):
        if 0 <= candidate < len(series.dates):
            delta = abs((series.dates[candidate] - target).days)
            if delta <= PRICE_TOLERANCE_DAYS and (best_delta is None or delta < best_delta):
                best = series.prices[candidate]
                best_delta = delta
    return best


def sentiment_verdict(sentiment: str, perf_pct: float | None, matured: bool) -> Verdict:
    if perf_pct is None or not matured:
        return "pending"
    if sentiment == "bullish":
        return "correct" if perf_pct > DIRECTIONAL_THRESHOLD_PCT else "incorrect"
    if sentiment == "bearish":
        return "correct" if perf_pct < -DIRECTIONAL_THRESHOLD_PCT else "incorrect"
    return "correct" if abs(perf_pct) <= NEUTRAL_BAND_PCT else "incorrect"


def hit_rate(verdicts: Sequence[Verdict]) -> float | None:
    decided = [v for v in verdicts if v != "pending"]
    if not decided:
        return None
    return round(100.0 * decided.count("correct") / len(decided), 1)


def earliest_price_date(notes: Sequence[Note]) -> date:
    return min(n.created_at.date() for n in notes) - timedelta(days=PRICE_TOLERANCE_DAYS)


def _horizon_result(
    series: PriceSeries, asset: AssetRef, sentiment: str, note_date: date, base: Decimal, horizon: int, today: date
) -> tuple[float | None, Verdict]:
    target = note_date + timedelta(days=horizon)
    matured = target <= today
    price = nearest_price(series, target) if matured else asset.current_price
    perf = float((price - base) / base * 100) if price is not None else None
    return (round(perf, 2) if perf is not None else None), sentiment_verdict(sentiment, perf, matured)


class _Accumulator:
    def __init__(self) -> None:
        self.entries: list[ScorecardEntry] = []
        self.unscorable = 0
        self.by_horizon: dict[int, list[Verdict]] = {h: [] for h in HORIZONS}
        self.by_sentiment: dict[str, list[Verdict]] = {s: [] for s in SCORED_SENTIMENTS}
        self.count_by_sentiment: dict[str, int] = dict.fromkeys(SCORED_SENTIMENTS, 0)

    def summary(self) -> ScorecardSummary:
        return ScorecardSummary(
            total_scored=len(self.entries),
            unscorable=self.unscorable,
            hit_rate_30d=hit_rate(self.by_horizon[30]),
            hit_rate_90d=hit_rate(self.by_horizon[90]),
            by_sentiment={
                s: ScorecardSentimentStats(n=self.count_by_sentiment[s], hit_rate=hit_rate(self.by_sentiment[s]))
                for s in SCORED_SENTIMENTS
            },
        )


def build_scorecard(
    notes: Sequence[Note], assets: dict[UUID, AssetRef], history: dict[str, PriceSeries], today: date
) -> ScorecardResponse:
    acc = _Accumulator()
    for note in notes:
        asset = assets.get(note.asset_id) if note.asset_id else None
        sentiment = note.sentiment
        if asset is None or not asset.symbol or sentiment is None:
            acc.unscorable += 1
            continue
        series = history.get(asset.symbol, PriceSeries())
        note_date = note.created_at.date()
        base = nearest_price(series, note_date)
        if base is None or base == 0:
            acc.unscorable += 1
            continue
        results = {h: _horizon_result(series, asset, sentiment, note_date, base, h, today) for h in HORIZONS}
        acc.entries.append(
            ScorecardEntry(
                note_id=note.id,
                title=note.title,
                symbol=asset.symbol,
                sentiment=sentiment,
                note_date=note_date,
                perf_30d=results[30][0],
                perf_90d=results[90][0],
                verdict_30d=results[30][1],
                verdict_90d=results[90][1],
            )
        )
        for horizon, (_, verdict) in results.items():
            acc.by_horizon[horizon].append(verdict)
            acc.by_sentiment[sentiment].append(verdict)
        acc.count_by_sentiment[sentiment] += 1
    return ScorecardResponse(entries=acc.entries, summary=acc.summary())
