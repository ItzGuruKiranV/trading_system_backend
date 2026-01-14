from dataclasses import dataclass
from datetime import datetime

@dataclass
class Candle:
    symbol: str
    timeframe: str   # "1m"
    time: datetime
    open: float
    high: float
    low: float
    close: float
