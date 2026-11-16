from dataclasses import dataclass, field
from datetime import datetime

PHASES = ("bearish", "bottom", "bullish", "top")
PHASES_6 = ("markdown", "bottoming", "accumulation", "markup", "topping", "distribution")


@dataclass
class IndicatorSignal:
    """Lecture d'un indicateur : phase qu'il désigne et force de 0 à 1."""

    name: str
    value: float
    signal: str
    strength: float
    description: str


@dataclass
class RegimeResult:
    """Probabilités des quatre phases d'un actif, phase dominante et confiance."""

    symbol: str
    probabilities: dict[str, float]
    dominant_regime: str
    confidence: float
    signals: list[IndicatorSignal]
    description: str


@dataclass
class RegimeConfig:
    """Paramètres de cycle tirés du régime, lus par le DCA, le filtre alpha, la santé et Monte-Carlo.

    ``risk_multiplier`` grossit les achats en marché baissier et les réduit en marché haussier.
    """

    risk_multiplier: float
    alpha_threshold: int
    gold_relevance: str
    mode_label: str
    vol_regime: str

    @staticmethod
    def from_regime(dominant_regime: str, confidence: float = 0.5) -> "RegimeConfig":
        """Configuration du régime ; sous 40 % de confiance, ramenée vers le mode normal."""
        cfg = RegimeConfig(*_BY_REGIME.get(dominant_regime, (1.0, 70, "medium", "Mode Normal", "normal")))
        if confidence < 0.4:
            cfg = RegimeConfig(
                risk_multiplier=round(0.6 * cfg.risk_multiplier + 0.4 * 1.0, 2),
                alpha_threshold=int(0.6 * cfg.alpha_threshold + 0.4 * 70),
                gold_relevance=cfg.gold_relevance,
                mode_label=cfg.mode_label,
                vol_regime="normal",
            )
        return cfg


_BY_REGIME: dict[str, tuple[float, int, str, str, str]] = {
    "bearish": (1.5, 85, "high", "Mode Accumulation Actif", "stress"),
    "markdown": (1.5, 85, "high", "Mode Accumulation Actif", "stress"),
    "distribution": (0.8, 80, "high", "Mode Prudence", "stress"),
    "bottom": (1.8, 75, "medium", "Mode Accumulation Fort", "normal"),
    "bottoming": (1.8, 75, "medium", "Mode Accumulation Fort", "normal"),
    "accumulation": (1.5, 70, "medium", "Mode Accumulation", "normal"),
    "bullish": (0.8, 60, "low", "Mode Expansion", "low"),
    "markup": (0.8, 60, "low", "Mode Expansion", "low"),
    "topping": (0.4, 75, "medium", "Mode Prise de Profits", "normal"),
    "top": (0.4, 75, "medium", "Mode Prise de Profits", "normal"),
}


@dataclass
class MarketRegime:
    """Régime du marché et de chaque actif."""

    market: RegimeResult
    per_asset: list[RegimeResult] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def config(self) -> RegimeConfig:
        """Configuration de cycle tirée du régime du marché."""
        return RegimeConfig.from_regime(self.market.dominant_regime, self.market.confidence)
