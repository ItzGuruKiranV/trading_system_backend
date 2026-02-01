from db.supabase_client import supabase

def fetch_trades(pair: str, year: str):
    """
    Fetch trades from Supabase.
    pair="ALL" -> fetch all pairs
    year="ALL" -> fetch all years
    """
    query = supabase.table("backtest_trades").select("*")

    # Filter by pair if not ALL
    if pair != "ALL":
        query = query.eq("pair", pair)

    # Filter by year if not ALL
    if year != "ALL":
        start = f"{year}-01-01"
        end = f"{year}-12-31"
        query = query.gte("trade_date", start).lte("trade_date", end)

    # Execute without 'ascending' keyword to avoid TypeError
    response = query.execute()

    # Sort manually in Python (ascending by trade_date)
    trades = response.data or []
    trades.sort(key=lambda t: t["trade_date"])

    return trades
