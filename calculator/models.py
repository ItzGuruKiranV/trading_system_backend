from pydantic import BaseModel


class LotSizeRequest(BaseModel):
    symbol: str
    account_balance: float
    risk_percent: float
    stop_loss_pips: float


class LotSizeResponse(BaseModel):
    lot_size: float
    pip_value_per_lot: float
    risk_amount: float
