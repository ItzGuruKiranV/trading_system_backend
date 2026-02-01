from fastapi import APIRouter, Query
from .service import get_backtest_data
from db.supabase_client import supabase



router = APIRouter(prefix="/backtest", tags=["Backtest"])

@router.get("/")
def get_backtest(
    pair: str = Query(..., example="EURUSD"),
    year: str = Query(..., example=2025),
):
    data = get_backtest_data(pair, year)
    if not data:
        return {"error": "No data found"}
    return data



@router.get("/pairs")
def get_backtest_pairs():
    response = supabase.table("backtest_trades").select("pair").execute()
    pairs = list(set(row["pair"] for row in response.data))
    pairs.sort()
    return pairs


@router.get("/years")
def get_backtest_years():
    # Fetch all trade dates
    response = supabase.table("backtest_trades").select("trade_date").execute()
    
    # Extract year from each trade_date
    years = set()
    for row in response.data:
        trade_date = row.get("trade_date")
        if trade_date:
            # Assuming trade_date is stored as ISO string: "YYYY-MM-DD"
            year = int(trade_date[:4])
            years.add(year)
    
    # Return sorted list
    return sorted(years)
