def resample_to_30m(data: pd.DataFrame) -> pd.DataFrame:
    """
    Resample 1-minute DataFrame to 30-minute OHLC DataFrame.
    """

    if data.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])

    df = data.copy()
    df = df.sort_index()

    out = []
    bucket = []
    current_block_start = None

    def thirty_min_block_start(t: pd.Timestamp) -> pd.Timestamp:
        block_minute = (t.minute // 30) * 30
        return t.replace(minute=block_minute, second=0, microsecond=0)

    for t, row in df.iterrows():
        this_block_start = thirty_min_block_start(t)

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

    df_30m = pd.DataFrame(out)
    df_30m.set_index("time", inplace=True)
    df_30m.sort_index(inplace=True)

    return df_30m
