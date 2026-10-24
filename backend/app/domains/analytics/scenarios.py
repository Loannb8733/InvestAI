from typing import TypedDict


class CrisisScenario(TypedDict):
    id: str
    name: str
    description: str
    shocks: dict[str, int]
    duration_days: int
    historical_recovery_months: int


HISTORICAL_SCENARIOS: list[CrisisScenario] = [
    {
        "id": "covid_2020",
        "name": "COVID-19 (Mars 2020)",
        "description": "Krach pandémique — chute rapide sur toutes les classes d'actifs en 30 jours",
        "shocks": {
            "crypto": -50,
            "stock": -35,
            "etf": -30,
            "real_estate": -10,
            "crowdfunding": -5,
        },
        "duration_days": 30,
        "historical_recovery_months": 5,
    },
    {
        "id": "luna_ftx_2022",
        "name": "LUNA/FTX (2022)",
        "description": "Effondrement crypto (Luna Mai + FTX Nov) — altcoins -60%, BTC -40%",
        "shocks": {
            "crypto": -60,
            "stock": -20,
            "etf": -15,
            "real_estate": -5,
            "crowdfunding": -3,
        },
        "duration_days": 60,
        "historical_recovery_months": 18,
    },
    {
        "id": "crisis_2008",
        "name": "Crise financière 2008",
        "description": "Crise systémique bancaire — chute massive des actions et immobilier",
        "shocks": {
            "crypto": -30,
            "stock": -50,
            "etf": -45,
            "real_estate": -25,
            "crowdfunding": -15,
        },
        "duration_days": 180,
        "historical_recovery_months": 48,
    },
    {
        "id": "bull_run_2021",
        "name": "Bull Run 2021",
        "description": "Hausse généralisée — crypto +100%, actions +25%, ETF +20%",
        "shocks": {
            "crypto": 100,
            "stock": 25,
            "etf": 20,
            "real_estate": 10,
            "crowdfunding": 5,
        },
        "duration_days": 365,
        "historical_recovery_months": 0,
    },
    {
        "id": "rate_hike",
        "name": "Hausse des taux (+300bp)",
        "description": "Resserrement monétaire brutal — impact sur les valorisations",
        "shocks": {
            "crypto": -25,
            "stock": -18,
            "etf": -15,
            "real_estate": -10,
            "crowdfunding": -5,
        },
        "duration_days": 90,
        "historical_recovery_months": 12,
    },
    {
        "id": "flash_crash",
        "name": "Flash Crash",
        "description": "Chute éclair intra-journalière sur tous les marchés",
        "shocks": {
            "crypto": -15,
            "stock": -10,
            "etf": -8,
            "real_estate": -3,
            "crowdfunding": -1,
        },
        "duration_days": 1,
        "historical_recovery_months": 1,
    },
]
