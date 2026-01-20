from fastapi import APIRouter, Query
from .service import get_backtest_data

router = APIRouter(prefix="/backtest", tags=["Backtest"])

@router.get("")
def get_backtest(
    pair: str = Query(..., examples="EURUSD"),
    year: int = Query(..., examples=2025),
):
    return get_backtest_data(pair, year)
