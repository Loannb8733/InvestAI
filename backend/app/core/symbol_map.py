"""Unified symbol-to-CoinGecko-ID mapping.

Single source of truth used by PriceService and HistoricalDataFetcher.
"""

from typing import Dict, Optional

# Overrides for Yahoo Finance crypto tickers that don't follow the {SYMBOL}-EUR pattern.
# Most cryptos use "{SYMBOL}-EUR" automatically; only add exceptions here.
YAHOO_CRYPTO_OVERRIDES: Dict[str, str] = {
    "PEPE": "PEPE24478-EUR",
}

# Stablecoins / fiat tokens — skip Yahoo fallback (price ≈ 1 €, not useful)
YAHOO_SKIP_SYMBOLS = {"USDC", "USDT", "USDG"}


def get_yahoo_symbol(symbol: str) -> Optional[str]:
    """Return the Yahoo Finance ticker for a crypto symbol, or None to skip.

    Uses the override map for special cases, otherwise defaults to {SYMBOL}-EUR.
    Skips stablecoins where Yahoo data adds no value.
    """
    symbol = symbol.upper()
    if symbol in YAHOO_SKIP_SYMBOLS:
        return None
    if symbol in YAHOO_CRYPTO_OVERRIDES:
        return YAHOO_CRYPTO_OVERRIDES[symbol]
    # Only generate Yahoo ticker for symbols we know are crypto (in COINGECKO_SYMBOL_MAP)
    if symbol in COINGECKO_SYMBOL_MAP:
        return f"{symbol}-EUR"
    return None


COINGECKO_SYMBOL_MAP: Dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "LINK": "chainlink",
    "AVAX": "avalanche-2",
    "UNI": "uniswap",
    "ATOM": "cosmos",
    "LTC": "litecoin",
    "ETC": "ethereum-classic",
    "PEPE": "pepe",
    "PAXG": "pax-gold",
    "SHIB": "shiba-inu",
    "ARB": "arbitrum",
    "OP": "optimism",
    "APT": "aptos",
    "INJ": "injective-protocol",
    "NEAR": "near",
    "FTM": "fantom",
    "ALGO": "algorand",
    "XLM": "stellar",
    "VET": "vechain",
    "FIL": "filecoin",
    "HBAR": "hedera-hashgraph",
    "ICP": "internet-computer",
    "SAND": "the-sandbox",
    "MANA": "decentraland",
    "AXS": "axie-infinity",
    "AAVE": "aave",
    "GRT": "the-graph",
    "CRV": "curve-dao-token",
    "MKR": "maker",
    "SNX": "synthetix-network-token",
    "COMP": "compound-governance-token",
    "SUSHI": "sushi",
    "YFI": "yearn-finance",
    "1INCH": "1inch",
    "ENJ": "enjincoin",
    "CHZ": "chiliz",
    "BAT": "basic-attention-token",
    "ZRX": "0x",
    "OCEAN": "ocean-protocol",
    "RNDR": "render-token",
    "IMX": "immutable-x",
    "LDO": "lido-dao",
    "RPL": "rocket-pool",
    "CRO": "crypto-com-chain",
    "KAVA": "kava",
    "RUNE": "thorchain",
    "ZEC": "zcash",
    "XMR": "monero",
    "DASH": "dash",
    "QTUM": "qtum",
    "ZIL": "zilliqa",
    "ENS": "ethereum-name-service",
    "GALA": "gala",
    "FLOW": "flow",
    "THETA": "theta-token",
    "EGLD": "elrond-erd-2",
    "XTZ": "tezos",
    "EOS": "eos",
    "NEO": "neo",
    "IOTA": "iota",
    "KSM": "kusama",
    "WAVES": "waves",
    "CELO": "celo",
    "ONE": "harmony",
    "ANKR": "ankr",
    "AUDIO": "audius",
    "BAND": "band-protocol",
    "STORJ": "storj",
    "SKL": "skale",
    "CTSI": "cartesi",
    "NMR": "numeraire",
    "OGN": "origin-protocol",
    "CELR": "celer-network",
    "SPELL": "spell-token",
    "JASMY": "jasmycoin",
    "TRX": "tron",
    "SUI": "sui",
    "SEI": "sei-network",
    "TIA": "celestia",
    "JUP": "jupiter-exchange-solana",
    "WIF": "dogwifcoin",
    "BONK": "bonk",
    "FLOKI": "floki",
    "BOME": "book-of-meme",
    "WLD": "worldcoin-wld",
    "STRK": "starknet",
    "BLUR": "blur",
    "PYTH": "pyth-network",
    "JTO": "jito-governance-token",
    "ORDI": "ordi",
    "STX": "stacks",
    "INS": "insure-defi",
    "TAO": "bittensor",
    "CGPT": "chaingpt",
    "USDG": "first-digital-usd",
    "FET": "fetch-ai",
    "USDC": "usd-coin",
    "USDT": "tether",
    "KAITO": "kaito",
    "OM": "mantra-dao",
    "ONDO": "ondo-finance",
    "PENDLE": "pendle",
    "TON": "the-open-network",
}
