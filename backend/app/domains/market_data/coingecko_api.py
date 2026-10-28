from app.core.config import settings

BASE_URL = "https://api.coingecko.com/api/v3"


def coingecko_headers() -> dict[str, str]:
    """En-têtes des appels CoinGecko ; avec une clé Demo, la limite de débit est celle de la clé, pas celle de l'IP."""
    headers = {"Accept": "application/json"}
    if settings.COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = settings.COINGECKO_API_KEY
    return headers
