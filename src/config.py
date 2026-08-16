from dataclasses import dataclass

SECTOR_ETFS = {
    "XLK": "Technology", "XLE": "Energy", "XLF": "Financials",
    "XLV": "Health Care", "XLI": "Industrials", "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples", "XLU": "Utilities", "XLB": "Materials",
    "XLRE": "Real Estate", "XLC": "Communication Services",
}
BENCHMARK = "SPY"

@dataclass(frozen=True)
class StrategyConfig:
    entry_score: float = 68.0
    hold_score: float = 48.0
    max_sectors: int = 3
    rebalance_weekday: int = 0
    trading_cost_bps: float = 10.0
    require_spy_above_200dma: bool = False
    risk_off_size_multiplier: float = 0.35
    weak_sector_rank_max: int = 5
    weakness_weight: float = 15.0
    stabilization_weight: float = 20.0
    relative_strength_weight: float = 25.0
    momentum_turn_weight: float = 15.0
    trend_weight: float = 15.0
    volume_weight: float = 10.0

DEFAULT_CONFIG = StrategyConfig()
