from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime

@dataclass
class PairState:
    symbol: str

    # 4H STRUCTURE
    trend_4h: str = "NEUTRAL"   # BULLISH / BEARISH
    last_swing_high: Optional[float] = None
    last_swing_low: Optional[float] = None

    bos_time_4h: Optional[datetime] = None

    # Pullback tracking
    phase: str = "WAITING"     # WAITING → PULLBACK → READY
    protected_high: Optional[float] = None
    protected_low: Optional[float] = None

    candidate_high: Optional[float] = None
    candidate_low: Optional[float] = None

    bearish_count: int = 0
    bullish_count: int = 0

    pullback_confirmed: bool = False

    # EVENT LOG (for frontend)
    events: List[dict] = field(default_factory=list)
