import pandas as pd

SEED_DAYS = 10
CANDLES_PER_DAY_4H = 6
SEED_CANDLES = SEED_DAYS * CANDLES_PER_DAY_4H


def detect_seed(df_4h: pd.DataFrame):
    """
    Implements full seed logic as specified.

    Returns:
        refined_df : DataFrame
        trend      : "BULLISH" | "BEARISH"
        break_time : Timestamp (exact break candle time)
    """

    df = df_4h.copy().sort_index()

    if len(df) < SEED_CANDLES + 5:
        raise ValueError("Not enough data for seed detection")

    # --------------------------------------------------
    # STEP 1 — TAKE FIRST 10 DAYS
    # --------------------------------------------------
    seed_df = df.iloc[:SEED_CANDLES]

    seed_high = seed_df["high"].max()
    seed_low = seed_df["low"].min()

    high_time = seed_df["high"].idxmax()
    low_time = seed_df["low"].idxmin()

    print("\n[SEED CONTEXT]")
    print(f"10D HIGH : {seed_high}")
    print(f"10D LOW  : {seed_low}")

    # --------------------------------------------------
    # STEP 2 — TEMP TREND
    # --------------------------------------------------
    if high_time > low_time:
        temp_trend = "BULLISH"
    else:
        temp_trend = "BEARISH"

    print(f"TEMP TREND : {temp_trend}")

    # --------------------------------------------------
    # STEP 3 — PULLBACK DETECTION
    # --------------------------------------------------
    pullback_active = False
    protected_level = None
    pullback_lows = []
    pullback_highs = []
    pullback_start_idx = None

    for i in range(SEED_CANDLES, len(df)):
        prev_candle = df.iloc[i - 1]
        candle = df.iloc[i]

        # -----------------------------
        # BULLISH TEMP TREND
        # -----------------------------
        if temp_trend == "BULLISH":
            is_pullback = (
                candle["close"] < candle["open"]
                and candle["low"] < prev_candle["high"]
            )

            if is_pullback:
                if not pullback_active:
                    protected_level = prev_candle["high"]
                    pullback_start_idx = i
                    pullback_active = True

                # protected high must NOT break
                if candle["high"] > protected_level:
                    pullback_active = False
                    pullback_lows.clear()
                    pullback_highs.clear()
                    continue

                pullback_lows.append(candle["low"])
                pullback_highs.append(candle["high"])

            if pullback_active and len(pullback_lows) >= 1:
                pullback_low = min(pullback_lows)
                pullback_high = max(pullback_highs)
                break

        # -----------------------------
        # BEARISH TEMP TREND
        # -----------------------------
        else:
            is_pullback = (
                candle["close"] > candle["open"]
                and candle["high"] > prev_candle["low"]
            )

            if is_pullback:
                if not pullback_active:
                    protected_level = prev_candle["low"]
                    pullback_start_idx = i
                    pullback_active = True

                # protected low must NOT break
                if candle["low"] < protected_level:
                    pullback_active = False
                    pullback_lows.clear()
                    pullback_highs.clear()
                    continue

                pullback_lows.append(candle["low"])
                pullback_highs.append(candle["high"])

            if pullback_active and len(pullback_highs) >= 1:
                pullback_low = min(pullback_lows)
                pullback_high = max(pullback_highs)
                break

    else:
        raise ValueError("Pullback not detected")

    print(f"PULLBACK CONFIRMED")
    print(f"Pullback High : {pullback_high}")
    print(f"Pullback Low  : {pullback_low}")

    # --------------------------------------------------
    # STEP 4 — WAIT FOR 10D HIGH / LOW BREAK
    # --------------------------------------------------
    for j in range(i + 1, len(df)):
        candle = df.iloc[j]
        t = df.index[j]

        # -------- BULLISH TEMP TREND --------
        if temp_trend == "BULLISH":

            # BOS → bullish confirmed
            if candle["high"] > seed_high:
                print(f"BOS ↑ at {t}")
                refined_df = df[df.index >= df[df["low"] == pullback_low].index[0]]
                return refined_df, "BULLISH", t

            # CHOCH → bearish
            if candle["low"] < seed_low:
                print(f"CHOCH ↓ at {t}")
                refined_df = df[df.index >= df[df["high"] == pullback_high].index[0]]
                return refined_df, "BEARISH", t

        # -------- BEARISH TEMP TREND --------
        else:

            # BOS → bearish confirmed
            if candle["low"] < seed_low:
                print(f"BOS ↓ at {t}")
                refined_df = df[df.index >= df[df["high"] == pullback_high].index[0]]
                return refined_df, "BEARISH", t

            # CHOCH → bullish
            if candle["high"] > seed_high:
                print(f"CHOCH ↑ at {t}")
                refined_df = df[df.index >= df[df["low"] == pullback_low].index[0]]
                return refined_df, "BULLISH", t

    raise ValueError("No break of 10-day high or low detected")
