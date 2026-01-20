from db.supabase_client import supabase

def fetch_trades(pair: str, year: int):
    start = f"{year}-01-01"
    end = f"{year}-12-31"

    res = (
        supabase
        .table("backtest_trades")
        .select("*")
        .eq("pair", pair)
        .gte("trade_date", start)
        .lte("trade_date", end)
        .order("trade_date")
        .execute()
    )

    return res.data or []
