from pydantic import BaseModel
from typing import List

class Trade(BaseModel):
    id: str
    date: str
    pair: str
    type: str
    entry: float
    exit: float
    pnl: float
    result: str

class SystemStats(BaseModel):
    winRate: float
    totalTrades: int
    profitFactor: float
    maxDrawdown: float
    netProfit: float
    averageWin: float
    averageLoss: float
    sharpeRatio: float
    trades: List[Trade]

class EquityPoint(BaseModel):
    date: str
    equity: float

class BacktestResponse(BaseModel):
    system1: SystemStats
    equityCurve: List[EquityPoint]
