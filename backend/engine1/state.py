from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class PairState:
    trend: Optional[str] = None

    bos_price: Optional[float] = None
    bos_time: Optional[datetime] = None

    choch_price: Optional[float] = None
    choch_time: Optional[datetime] = None

    pullback_price: Optional[float] = None
    pullback_time: Optional[datetime] = None
    pullback_candle_count: int = 0
