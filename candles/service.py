from db.supabase_client import supabase

# 🔹 Map timeframe → table name
TF_TABLE_MAP = {
    "1m": "candles_1m",
    "5m": "candles_5m",
    "20m": "candles_20m",
    "4h": "candles_4h",   # change if your table name differs
}


def fetch_candles(symbol: str, tf: str, limit: int):
    if tf not in TF_TABLE_MAP:
        raise ValueError("Unsupported timeframe")

    table = TF_TABLE_MAP[tf]

    res = (
        supabase
        .table(table)
        .select("timestamp, open, high, low, close")
        .eq("symbol", symbol)
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
    )

    # Supabase returns newest first → reverse for chart
    data = list(reversed(res.data))

    return data
