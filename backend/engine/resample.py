from datetime import datetime
import pandas as pd


def resample_to_4h(data: pd.DataFrame) -> pd.DataFrame:
    """
    Resample 1-minute DataFrame to 4-hour OHLC DataFrame.
    """

    if data.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])

    df = data.copy()
    df = df.sort_index()

    out = []
    bucket = []
    current_block_start = None

    def four_hour_block_start(t: pd.Timestamp) -> pd.Timestamp:
        block_hour = (t.hour // 4) * 4
        return t.replace(hour=block_hour, minute=0, second=0, microsecond=0)

    for t, row in df.iterrows():
        this_block_start = four_hour_block_start(t)

        if current_block_start is None:
            current_block_start = this_block_start

        if this_block_start != current_block_start and bucket:
            out.append({
                "time": bucket[0][0],
                "open": bucket[0][1]["open"],
                "high": max(x[1]["high"] for x in bucket),
                "low":  min(x[1]["low"]  for x in bucket),
                "close": bucket[-1][1]["close"],
            })
            bucket = []
            current_block_start = this_block_start

        bucket.append((t, row))

    if bucket:
        out.append({
            "time": bucket[0][0],
            "open": bucket[0][1]["open"],
            "high": max(x[1]["high"] for x in bucket),
            "low":  min(x[1]["low"]  for x in bucket),
            "close": bucket[-1][1]["close"],
        })

    df_4h = pd.DataFrame(out)
    df_4h.set_index("time", inplace=True)
    df_4h.sort_index(inplace=True)

    return df_4h



def resample_to_5m(data: pd.DataFrame) -> pd.DataFrame:
    """
    Resample 1-minute DataFrame to 5-minute OHLC DataFrame.
    """

    if data.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])

    df = data.copy()
    df = df.sort_index()

    out = []
    bucket = []
    current_block_start = None

    def five_minute_block_start(t: pd.Timestamp) -> pd.Timestamp:
        block_minute = (t.minute // 5) * 5
        return t.replace(minute=block_minute, second=0, microsecond=0)

    for t, row in df.iterrows():
        this_block_start = five_minute_block_start(t)

        if current_block_start is None:
            current_block_start = this_block_start

        if this_block_start != current_block_start and bucket:
            out.append({
                "time": bucket[0][0],
                "open": bucket[0][1]["open"],
                "high": max(x[1]["high"] for x in bucket),
                "low":  min(x[1]["low"]  for x in bucket),
                "close": bucket[-1][1]["close"],
            })
            bucket = []
            current_block_start = this_block_start

        bucket.append((t, row))

    if bucket:
        out.append({
            "time": bucket[0][0],
            "open": bucket[0][1]["open"],
            "high": max(x[1]["high"] for x in bucket),
            "low":  min(x[1]["low"]  for x in bucket),
            "close": bucket[-1][1]["close"],
        })

    df_5m = pd.DataFrame(out)
    df_5m.set_index("time", inplace=True)
    df_5m.sort_index(inplace=True)

    return df_5m
