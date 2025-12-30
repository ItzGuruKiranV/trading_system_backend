from fastapi import APIRouter, Query, HTTPException
from candles.service import fetch_candles

router = APIRouter(prefix="/api/candles", tags=["Candles"])


@router.get("")
def get_candles(
    symbol: str = Query(...),
    tf: str = Query(...),
    limit: int = Query(200, ge=10, le=5000),
):
    try:
        return fetch_candles(symbol, tf, limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
