import pandas as pd
from typing import List, Dict
def process_structure_and_return_last_swing(
    df: pd.DataFrame,
    trend: str,
    min_pullback_candles: int = 2,
    retrace_pct: float = 0.99,
):

    highs = df["high"].values
    lows = df["low"].values
    opens = df["open"].values
    closes = df["close"].values
    times = df.index

    is_bullish = trend.lower() == "bullish"

    # --------------------------------
    # INITIAL STRUCTURE
    # --------------------------------
    if is_bullish:
            swing_low = lows[0]
    else:
            swing_high = highs[0]

    temp_high = None
    temp_high_idx = None

    temp_low = None
    temp_low_idx = None

    pullback_count = 0
    swings: List[Dict] = []

    pullback_started = False
    valid_pullback=False

    last_confirmed_swing_high = None
    last_confirmed_swing_low = None
    # --------------------------------
    # MAIN LOOP
    # --------------------------------
    for i in range(1, len(df)):

        high = highs[i]
        low = lows[i]
        open_ = opens[i]
        close = closes[i]
        time = times[i]

        is_bull_candle = close > open_
        is_bear_candle = close < open_


        # ==================================================
        # 🔵 BULLISH STRUCTURE
        # ==================================================
        if is_bullish:

            # Track impulse high
            if (temp_high is None or high > temp_high) and (pullback_count == 0 or pullback_count == 1):
                temp_high = high
                temp_high_idx = i
                pullback_count = 0
                continue

            # Pullback detection
            if is_bear_candle:
                pullback_count += 1

            retrace = (temp_high - low) / max(temp_high - swing_low, 1e-9)

            valid_pullback = (
                pullback_count >= min_pullback_candles
                or retrace >= retrace_pct
            )



            # ---------------------------
            # BOS → CONFIRM SWINGS
            # ---------------------------
            if valid_pullback and high > temp_high:

                swing_high = temp_high
                swings.append({
                    "type": "swing_high",
                    "time": times[temp_high_idx],
                    "price": swing_high
                })

                swing_low = lows[temp_high_idx:i+1].min()
                swings.append({
                    "type": "swing_low",
                    "time": time,
                    "price": swing_low
                })

                temp_high = high
                temp_high_idx = i
                pullback_count = 0
                last_confirmed_swing_high = None

            # CHOCH
            if valid_pullback and low < swing_low:
                swing_high = temp_high
                swings.append({
                    "type": "swing_high",
                    "time": times[temp_high_idx],
                    "price": swing_high
                })
                is_bullish = False
                temp_low = low
                temp_low_idx = i
                pullback_count = 0

        # ==================================================
        # 🔴 BEARISH STRUCTURE
        # ==================================================
        else:

            # Track impulse low
            if (temp_low is None or low < temp_low) and (pullback_count == 0 or pullback_count == 1):
                temp_low = low
                temp_low_idx = i
                pullback_count = 0
                continue

            # Pullback detection
            if is_bull_candle:
                pullback_count += 1

            retrace = (high - temp_low) / max(swing_high - temp_low, 1e-9)

            valid_pullback = (
                pullback_count >= min_pullback_candles
                or retrace >= retrace_pct
            )
            # ---------------------------
            # BOS → CONFIRM SWINGS
            # ---------------------------
            if valid_pullback and low < temp_low:

                swing_low = temp_low
                swings.append({
                    "type": "swing_low",
                    "time": times[temp_low_idx],
                    "price": swing_low
                })

                swing_high = highs[temp_low_idx:i+1].max()
                swings.append({
                    "type": "swing_high",
                    "time": time,
                    "price": swing_high
                })

                temp_low = low
                temp_low_idx = i
                pullback_count = 0

            # CHOCH
            if valid_pullback and high > swing_high:
                swing_low = temp_low
                swings.append({
                    "type": "swing_low",
                    "time": times[temp_low_idx],
                    "price": swing_low
                })
                is_bullish = True
                temp_high = high
                temp_high_idx = i
                pullback_count = 0

    final_level = swing_low if trend.lower() is "bullish" else swing_high
    return final_level