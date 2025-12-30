from pydantic import BaseModel
from typing import Optional


class JournalBase(BaseModel):
    trade_date: str
    day_of_week: str
    session: str
    timeframe: str
    symbol: str
    system: str
    direction: str
    entry_price: float
    exit_price: float
    pnl: float
    result: str
    hold_minutes: int
    emotion: str
    notes: Optional[str] = None
    screenshot_url: Optional[str] = None


class JournalCreate(JournalBase):
    pass


class JournalOut(JournalBase):
    id: int
