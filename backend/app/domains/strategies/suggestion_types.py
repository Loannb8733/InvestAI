from typing import Any

AssetRow = dict[str, Any]
Suggestion = dict[str, Any]

BEAR_REGIMES = ("bearish", "bottom", "accumulation", "markdown")
BULL_REGIMES = ("bullish", "markup")


def asset_count(count: int) -> str:
    return f"{count} actif" if count == 1 else f"{count} actifs"
