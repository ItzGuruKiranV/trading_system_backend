import pandas as pd


def process_structure_and_return_last_swing(
    df: pd.DataFrame,
    trend: str,
    min_pullback_candles: int = 2,
    retrace_pct: float = 0.35,
):
    """
    Maps market structure on sliced DF.

    Rules:
    - Bullish  → returns latest SWING LOW price
    - Bearish  → returns latest SWING HIGH price
    - BOS / CHOCH printed
    - Pullback = 2 opposite candles OR 35% retracement
    """

    highs = df["high"].values
    lows = df["low"].values
    opens = df["open"].values
    closes = df["close"].values
    idxs = df.index

    is_bullish = trend.lower() == "bullish"

    # --------------------------------
    # INITIAL SWINGS (FIRST CANDLE)
    # --------------------------------
    swing_high = highs[0]
    swing_low = lows[0]

    last_confirmed_swing_high = None
    last_confirmed_swing_low = None

    pullback_count = 0

    print("\n====== STRUCTURE TRACE ======")
    print(f"Initial Trend: {trend.upper()}")
    print(f"Initial Swing High: {swing_high}")
    print(f"Initial Swing Low : {swing_low}\n")

    # --------------------------------
    # MAIN LOOP
    # --------------------------------
    for i in range(1, len(df)):

        high = highs[i]
        low = lows[i]
        open_ = opens[i]
        close = closes[i]
        time = idxs[i]

        is_bull_candle = close > open_
        is_bear_candle = close < open_

        # ===============================
        # BULLISH STRUCTURE
        # ===============================
        if is_bullish:

            # Track new highs
            if high > swing_high:
                swing_high = high
                pullback_count = 0

            # Pullback detection
            if is_bear_candle:
                pullback_count += 1
            else:
                pullback_count = 0

            retrace = (swing_high - low) / max(swing_high - swing_low, 1e-9)

            valid_pullback = (
                pullback_count >= min_pullback_candles
                or retrace >= retrace_pct
            )

            # BOS → higher high after pullback
            if valid_pullback and high > swing_high:
                last_confirmed_swing_low = swing_low
                swing_high = high
                pullback_count = 0


            # Update swing low only AFTER BOS
            if valid_pullback and low < swing_low:
                swing_low = low

            # CHOCH → break below swing low
            if low < swing_low:
                is_bullish = False
                pullback_count = 0

        # ===============================
        # BEARISH STRUCTURE
        # ===============================
        else:

            # Track new lows
            if low < swing_low:
                swing_low = low
                pullback_count = 0

            # Pullback detection
            if is_bull_candle:
                pullback_count += 1
            else:
                pullback_count = 0

            retrace = (high - swing_low) / max(swing_high - swing_low, 1e-9)

            valid_pullback = (
                pullback_count >= min_pullback_candles
                or retrace >= retrace_pct
            )

            # BOS → lower low after pullback
            if valid_pullback and low < swing_low:
                last_confirmed_swing_high = swing_high
                swing_low = low
                pullback_count = 0


            # Update swing high only AFTER BOS
            if valid_pullback and high > swing_high:
                swing_high = high

            # CHOCH → break above swing high
            if high > swing_high:
                is_bullish = True
                pullback_count = 0

    # --------------------------------
    # FINAL RETURN
    # --------------------------------
    print("\n====== FINAL STRUCTURE ======")

    if is_bullish:
        protected_low = (
            last_confirmed_swing_low
            if last_confirmed_swing_low is not None
            else swing_low
        )

        print("Final Trend: BULLISH")
        print(f"Protected Swing LOW: {protected_low}")
        return protected_low
    else:
        protected_high = (
            last_confirmed_swing_high
            if last_confirmed_swing_high is not None
            else swing_high
        )

        print("Final Trend: BEARISH")
        print(f"Protected Swing HIGH: {protected_high}")
        return protected_high

