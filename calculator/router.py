from fastapi import APIRouter, HTTPException

from calculator.models import LotSizeRequest, LotSizeResponse
from calculator.service import calculate_lot_size

router = APIRouter(prefix="/api/lot-size", tags=["Calculator"])


@router.post("", response_model=LotSizeResponse)
def lot_size_api(data: LotSizeRequest):
    try:
        return calculate_lot_size(
            symbol=data.symbol,
            account_balance=data.account_balance,
            risk_percent=data.risk_percent,
            stop_loss_pips=data.stop_loss_pips,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
