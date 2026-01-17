from dataclasses import dataclass, field
from typing import Optional, Literal,List
from datetime import datetime

@dataclass
class PairState:
    symbol: str

    # 4H STRUCTURE
    trend_4h: str = "NEUTRAL"   # BULLISH / BEARISH / NEUTRAL
    
    swing_high: Optional[float] = None
    swing_low: Optional[float] = None

    choch_level_4h: Optional[float] = None 
    bos_level_4h: Optional[float] = None  # BOS candle level (price)
    bos_time_4h: Optional[datetime] = None
    h4_structure_event : Optional[Literal["BOS", "CHOCH"]] = None

    # Pullback tracking
    phase: str = "WAITING"     # WAITING → PULLBACK → READY
    trade_active: bool = False 
    protected_high: Optional[float] = None
    protected_low: Optional[float] = None

    candidate_high: Optional[float] = None
    candidate_low: Optional[float] = None

    bearish_count: int = 0
    bullish_count: int = 0

    pullback_confirmed: bool = False
    pullback_time: Optional[datetime] = None

    # Pullback config (set in run1.py, now part of state)
    pullback_pct: float = 0.02
    min_pullback_candles: int = 2

    # EVENT LOG (for frontend / history)
    events: List[dict] = field(default_factory=list)

    # Buffers for incremental aggregation
    buffer_5m: List[dict] = field(default_factory=list)
    buffer_4h: List[dict] = field(default_factory=list)
    # -----------------------------
    # 5M STRUCTURE & SWINGS
    # -----------------------------
    swing_high_5m: Optional[float] = None
    swing_high_5m_time: Optional[datetime] = None
    swing_low_5m: Optional[float] = None
    swing_low_5m_time: Optional[datetime] = None

    candidate_high_5m: Optional[float] = None
    candidate_low_5m: Optional[float] = None
    pullback_count_5m: int = 0

    buffer_5m_sh: List[dict] = field(default_factory=list)  # swing high / low buffer
    buffer_5m_sl: List[dict] = field(default_factory=list)  # swing low / high buffer
    buffer_5m_poi: List[dict] = field(default_factory=list)  # 5M candles for POI mapping

    trend_5m: str = "NEUTRAL"  # current 5M trend

    # -----------------------------
    # POI / TAP / PROTECTION
    # -----------------------------
    mapped_pois: List[dict] = field(default_factory=list)
    active_poi: Optional[dict] = None
    poi_tapped: bool = False
    poi_tapped_level: Optional[float] = None
    poi_tapped_time: Optional[datetime] = None

    protected_5m_point: Optional[float] = None
    protected_5m_time: Optional[datetime] = None

    poi_invalidated: bool = False  # flag if active POI got invalidated

    # -----------------------------
    # TRADE / CHOCH
    # -----------------------------
    trade: Optional[dict] = None  # stores the planned trade details
    trade_planned: bool = False
    entry_filled: bool = False

    choch_5m_this_candle: bool = False  # flag to mark the exact candle where 5M CHOCH occurred
