import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.domains.predictions.core import PredictionCore

logger = logging.getLogger(__name__)

Event = dict[str, Any]

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
FOREX_FACTORY_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
ECB_URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
BLOCK_COUNT_URL = "https://blockchain.info/q/getblockcount"
FOMC_PATTERN = rf"({'|'.join(MONTHS.keys())})\s+(\d{{1,2}})-(\d{{1,2}})\*?"
ECB_PATTERN = (
    r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})"
)
QUARTER_ENDS = [(3, 31, "Q1"), (6, 30, "Q2"), (9, 30, "Q3"), (12, 31, "Q4")]
HALVING_INTERVAL = 210_000
MAX_EVENTS = 15


def _event(title: str, date: str, category: str, description: str, impact: str, days_until: int) -> Event:
    return {
        "title": title,
        "date": date,
        "category": category,
        "description": description,
        "impact": impact,
        "days_until": days_until,
    }


def _forex_event(item: Any, now: datetime) -> Event | None:
    impact = item.get("impact", "")
    if impact not in ("High", "Medium"):
        return None
    date_str = item.get("date", "")
    if not date_str:
        return None
    try:
        evt_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None
    if evt_date < now:
        return None
    country = item.get("country", "")
    title = item.get("title", "Événement économique")
    forecast = item.get("forecast", "")
    previous = item.get("previous", "")
    desc_parts = []
    if country:
        desc_parts.append(country)
    if previous:
        desc_parts.append(f"Précédent: {previous}")
    if forecast:
        desc_parts.append(f"Prévision: {forecast}")
    description = " — ".join(desc_parts) if desc_parts else title
    impact_level = "high" if impact == "High" else "medium"
    return _event(title, evt_date.strftime("%Y-%m-%d"), "macro", description, impact_level, (evt_date - now).days)


async def _add_forex_events(events: list[Event], now: datetime) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(FOREX_FACTORY_URL)
            resp.raise_for_status()
            data = resp.json()
        for item in data:
            event = _forex_event(item, now)
            if event is not None:
                events.append(event)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to fetch Forex Factory calendar: %s", e)


def _fomc_section(html: str, year: int) -> str | None:
    year_section_match = re.search(rf'class="[^"]*"[^>]*>\s*{year}\s*<', html, re.IGNORECASE)
    if not year_section_match:
        return None
    start = year_section_match.start()
    next_year = re.search(rf'class="[^"]*"[^>]*>\s*{year + 1}\s*<', html[start + 100 :], re.IGNORECASE)
    end = start + 100 + next_year.start() if next_year else len(html)
    return html[start:end]


def _add_fomc_year(events: list[Event], section: str, year: int, now: datetime) -> None:
    for match in re.finditer(FOMC_PATTERN, section, re.IGNORECASE):
        month = MONTHS.get(match.group(1).lower())
        if not month:
            continue
        try:
            evt_date = datetime(year, month, int(match.group(3)))
        except ValueError:
            continue
        if evt_date < now:
            continue
        events.append(
            _event(
                "Réunion FOMC (Fed)",
                evt_date.strftime("%Y-%m-%d"),
                "macro",
                "Décision sur les taux d'intérêt américains",
                "high",
                (evt_date - now).days,
            )
        )


async def _add_fomc_events(events: list[Event], now: datetime) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(FOMC_URL)
            resp.raise_for_status()
            html = resp.text
        for year in [now.year, now.year + 1]:
            section = _fomc_section(html, year)
            if section is not None:
                _add_fomc_year(events, section, year, now)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to scrape FOMC calendar: %s", e)


def _ecb_date(match: re.Match[str], now: datetime) -> datetime | None:
    day = int(match.group(1))
    month = MONTHS.get(match.group(2).lower())
    year = int(match.group(3))
    if not month or year < now.year:
        return None
    try:
        evt_date = datetime(year, month, day)
    except ValueError:
        return None
    return None if evt_date < now else evt_date


def _add_ecb_section(events: list[Event], chunk: str, seen: set[str], now: datetime) -> None:
    for match in re.finditer(ECB_PATTERN, chunk, re.IGNORECASE):
        evt_date = _ecb_date(match, now)
        if evt_date is None:
            continue
        date_key = evt_date.strftime("%Y-%m-%d")
        if date_key in seen:
            continue
        seen.add(date_key)
        events.append(
            _event(
                "Réunion BCE",
                date_key,
                "macro",
                "Décision sur les taux d'intérêt européens",
                "high",
                (evt_date - now).days,
            )
        )


async def _add_ecb_events(events: list[Event], now: datetime) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(ECB_URL)
            resp.raise_for_status()
            html = resp.text
        seen: set[str] = set()
        for section in re.split(r"(?i)monetary\s+polic", html)[1:]:
            _add_ecb_section(events, section[:800], seen, now)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to scrape ECB calendar: %s", e)


def _add_quarter_ends(events: list[Event], now: datetime) -> None:
    for year in [now.year, now.year + 1]:
        for m, d, label in QUARTER_ENDS:
            evt_date = datetime(year, m, d)
            if evt_date < now or (evt_date - now).days > 365:
                continue
            events.append(
                _event(
                    f"Fin de trimestre {label}",
                    evt_date.strftime("%Y-%m-%d"),
                    "fiscal",
                    f"Clôture {label} — rééquilibrages institutionnels",
                    "medium",
                    (evt_date - now).days,
                )
            )


async def _add_halving(events: list[Event], now: datetime) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(BLOCK_COUNT_URL)
            if resp.status_code != 200:
                return
            current_block = int(resp.text.strip())
            next_halving_block = ((current_block // HALVING_INTERVAL) + 1) * HALVING_INTERVAL
            est_halving_date = now + timedelta(minutes=(next_halving_block - current_block) * 10)
            if (est_halving_date - now).days > 0:
                events.append(
                    _event(
                        f"Halving Bitcoin #{next_halving_block // HALVING_INTERVAL}",
                        est_halving_date.strftime("%Y-%m-%d"),
                        "crypto",
                        f"Réduction de la récompense de minage — bloc {next_halving_block:,}",
                        "high",
                        (est_halving_date - now).days,
                    )
                )
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to fetch BTC block height: %s", e)


def _unique_soonest(events: list[Event]) -> list[Event]:
    seen = set()
    unique = []
    for e in events:
        key = (e["title"], e["date"])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    unique.sort(key=lambda x: x["days_until"])
    return unique[:MAX_EVENTS]


class EventsMixin(PredictionCore):
    async def get_market_events(self) -> list[dict[str, Any]]:
        """Quinze prochains événements de marché : calendrier Forex Factory de la semaine (impact moyen ou fort),
        réunions FOMC et BCE lues sur leurs sites, fins de trimestre et prochain halving estimé à 10 min par bloc."""
        now = datetime.now(UTC).replace(tzinfo=None)
        events: list[Event] = []
        await _add_forex_events(events, now)
        await _add_fomc_events(events, now)
        await _add_ecb_events(events, now)
        _add_quarter_ends(events, now)
        await _add_halving(events, now)
        return _unique_soonest(events)
