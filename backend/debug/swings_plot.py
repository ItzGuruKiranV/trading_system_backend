import matplotlib.pyplot as plt
import pandas as pd
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# =========================
# Dataclass
# =========================
@dataclass
class swing_state:
    index: int
    time: Any
    trend: str
    event: str
    validation_tf: Optional[str] = None
    swing_high: Optional[float] = None
    swing_low: Optional[float] = None
    active_poi: Optional[Dict] = None
    trade_details: Optional[Dict] = None
    rr_ratio: Optional[float] = None
    liquidity_grabbed: bool = False
    extra: Dict = field(default_factory=dict)