import pandas as pd
import sys
import os



SEED_DAYS = 10
CANDLES_PER_DAY_4H = 6
SEED_CANDLES = SEED_DAYS * CANDLES_PER_DAY_4H

from dataclasses import dataclass
from typing import Optional, List

@dataclass
class CandleState:
    index: int
    time: pd.Timestamp
    temp_trend: str
    pullback_active: bool
    protected_level: Optional[float] = None  # ← ADD DEFAULT
    seed_high: float = 0.0                   # ← ADD DEFAULT
    seed_low: float = 0.0                    # ← ADD DEFAULT
    pullback_low: float = float('inf')       # ← NEW: Required for seed_plot.py
    pullback_high: float = float('-inf')     # ← NEW: Required for seed_plot.py
    event: Optional[str] = None
    pullback_start_idx: Optional[int] = None
    seed_complete: bool = False

def detect_seed(df_4h: pd.DataFrame):
    """
    Implements full seed logic as specified.

    Returns:
        refined_df : DataFrame
        trend      : "BULLISH" | "BEARISH"
        break_time : Timestamp (exact break candle time)
        break_idx  : int (break candle index)
        states     : List[CandleState]  # NEW: for animation
    """
    
    df = df_4h.copy().sort_index()

    if len(df) < SEED_CANDLES + 5:
        raise ValueError("Not enough data for seed detection")

    states = []
    

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

    for i in range(SEED_CANDLES):
        seed_complete = (i == SEED_CANDLES - 1)
        state=CandleState(
            index=i, time=df.index[i], temp_trend=temp_trend,
            pullback_active=False, protected_level=None,
            seed_high=seed_high, seed_low=seed_low,
            seed_complete=seed_complete
        )
        states.append(state)


    # --------------------------------------------------
    # STEP 3 — PULLBACK DETECTION
    # --------------------------------------------------
    pullback_active = False
    protected_level = None
    pullback_lows = []
    pullback_highs = []
    pullback_start_idx = None
    pullback_confirm_idx = None
    final_pullback_low = float('inf')
    final_pullback_high = float('-inf')

    for i in range(SEED_CANDLES, len(df)):
        prev_candle = df.iloc[i - 1]
        candle = df.iloc[i]

        # Base state BEFORE logic
        current_pullback_low = min(pullback_lows) if pullback_lows else float('inf')
        current_pullback_high = max(pullback_highs) if pullback_highs else float('-inf')

        state = CandleState(
            index=i, time=df.index[i], temp_trend=temp_trend,
            pullback_active=pullback_active, protected_level=protected_level,
            seed_high=seed_high, seed_low=seed_low,
            pullback_low=current_pullback_low, pullback_high=current_pullback_high,
            event=None, pullback_start_idx=pullback_start_idx, seed_complete=True
        )
        states.append(state)

        

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
                    state.event = "PULLBACK_START"
                    continue
                
                # protected high must NOT break
                if pullback_active:
                    if candle["high"] > protected_level:
                        # 🔥 PULLBACK RESET
                        state.event = "PULLBACK_RESET"
                        pullback_active = False
                        protected_level = None
                        pullback_lows.clear()
                        pullback_highs.clear()
                        continue
                    else:
                        pullback_lows.append(candle["low"])
                        pullback_highs.append(candle["high"])

            if pullback_active and len(pullback_lows) >= 1:
                final_pullback_low = min(pullback_lows)
                final_pullback_high = max(pullback_highs)
                state.pullback_low = final_pullback_low
                state.pullback_high = final_pullback_high
                state.event = "PULLBACK_CONFIRMED"
                pullback_confirm_idx = i
                break

        # -----------------------------
        # BEARISH TEMP TREND
        # -----------------------------
        else:
            is_pullback = (
                candle["close"] > candle["open"]
                and candle["high"] > prev_candle["low"]
            )

            if is_pullback and not pullback_active:
                protected_level = prev_candle["low"]
                pullback_start_idx = i
                pullback_active = True
                state.event = "PULLBACK_START"
                continue

            if pullback_active:
                if candle["low"] < protected_level:
                    state.event = "PULLBACK_RESET"
                    pullback_active = False
                    protected_level = None
                    pullback_lows.clear()
                    pullback_highs.clear()
                    continue
                else:
                    pullback_lows.append(candle["low"])
                    pullback_highs.append(candle["high"])

            if pullback_active and len(pullback_highs) >= 1:
                final_pullback_low = min(pullback_lows)
                final_pullback_high = max(pullback_highs)
                state.pullback_low = final_pullback_low
                state.pullback_high = final_pullback_high
                state.event = "PULLBACK_CONFIRMED"
                pullback_confirm_idx = i
                break


    else:
        raise ValueError("Pullback not detected")

    print(f"PULLBACK CONFIRMED at index {pullback_confirm_idx}")
    print(f"Pullback High : {final_pullback_high}")
    print(f"Pullback Low  : {final_pullback_low}")

# --------------------------------------------------
# STEP 4 — WAIT FOR 10D HIGH / LOW BREAK
# --------------------------------------------------
    for j in range(pullback_confirm_idx + 1, len(df)):
        candle = df.iloc[j]
        t = df.index[j]
        state = CandleState(
            index=j, time=t, temp_trend=temp_trend, pullback_active=False,
            protected_level=None, seed_high=seed_high, seed_low=seed_low,
            pullback_low=final_pullback_low, pullback_high=final_pullback_high,
            event=None, pullback_start_idx=pullback_start_idx, seed_complete=True
        )
        states.append(state)

        if temp_trend == "BULLISH":
            if candle["high"] > seed_high:
                print(f"BOS ↑ at {t}")
                state.event = "BOS"
                # slice from seed extreme
                # ✅ REPLACE PULLBACK CUT LOGIC
                if temp_trend == "BULLISH":
                    # ✅ Find HL between seed high and BOS
                    slice_df = df.loc[high_time : t]

                    if not slice_df.empty:
                        cut_time = slice_df["low"].idxmin()
                    else:
                        cut_time = high_time  # fallback safety
                cut_idx = df.index.get_indexer([cut_time], method="ffill")[0]
                refined_df = df.iloc[cut_idx:]

                # 🔍 DEBUG: print seed extreme and refined DF first candle
                print("📌 STRUCTURE START (BULLISH BOS)")
                print(f"Swing LOW (HL) taken at: {cut_time}")
                print(f"HL Price: {df.loc[cut_time]['low']}")

                # 🔥 KEEP OPEN AFTER BOS!
                print("🎉 BOS CONFIRMED! Plot stays open FOREVER!")
                print("📊 Close window → continues to Market Structure phase")
                return refined_df, "BULLISH", t, j, states
            
            if candle["low"] < seed_low:
                print(f"CHOCH ↓ at {t}")
                state.event = "CHOCH"
                # slice from seed extreme
                # ✅ REPLACE PULLBACK CUT LOGIC
                # ✅ FIND SWING HIGH BETWEEN SEED HIGH AND CHOCH
                choch_time = t

                range_df = df.loc[high_time:choch_time]

                swing_high_price = range_df["high"].max()
                swing_high_time = range_df["high"].idxmax()

                cut_time = swing_high_time
                cut_price = swing_high_price
               
                cut_idx = df.index.get_indexer([cut_time], method="ffill")[0]
                refined_df = df.iloc[cut_idx:]

                # 🔍 DEBUG: print swing extreme and refined DF first candle
                print(f"Swing HIGH taken at: {cut_time}, price: {cut_price}")
                print(
                    f"Refined DF starts at: {refined_df.index[0]} | "
                    f"O:{refined_df.iloc[0]['open']} "
                    f"H:{refined_df.iloc[0]['high']} "
                    f"L:{refined_df.iloc[0]['low']} "
                    f"C:{refined_df.iloc[0]['close']}"
                )

                print("🎉 CHOCH CONFIRMED! Plot stays open FOREVER!")
                print("📊 Close window → continues...")
                return refined_df, "BEARISH", t, j, states
        
        else:  # BEARISH
            if candle["low"] < seed_low:
                print(f"BOS ↓ at {t}")
                state.event = "BOS"
                # slice from seed extreme
                # ✅ REPLACE PULLBACK CUT LOGIC
                # ✅ FIND SWING HIGH BETWEEN SEED LOW AND BOS
                bos_time = t

                range_df = df.loc[low_time:bos_time]

                swing_high_price = range_df["high"].max()
                swing_high_time = range_df["high"].idxmax()

                cut_time = swing_high_time
                cut_price = swing_high_price
                cut_idx = df.index.get_indexer([cut_time], method="ffill")[0]
                refined_df = df.iloc[cut_idx:]


                print(
                    f"Refined DF starts at: {refined_df.index[0]} | "
                    f"O:{refined_df.iloc[0]['open']} "
                    f"H:{refined_df.iloc[0]['high']} "
                    f"L:{refined_df.iloc[0]['low']} "
                    f"C:{refined_df.iloc[0]['close']}"
                )

                print("🎉 BOS CONFIRMED! Plot stays open FOREVER!")
                return refined_df, "BEARISH", t, j, states
            
            if candle["high"] > seed_high:
                print(f"CHOCH ↑ at {t}")
                state.event = "CHOCH"
                # slice from seed extreme
                # ✅ REPLACE PULLBACK CUT LOGIC
                # ✅ FIND SWING LOW BETWEEN SEED LOW AND CHOCH
                choch_time = t

                range_df = df.loc[low_time:choch_time]

                swing_low_price = range_df["low"].min()
                swing_low_time = range_df["low"].idxmin()

                cut_time = swing_low_time
                cut_price = swing_low_price
                cut_idx = df.index.get_indexer([cut_time], method="ffill")[0]
                refined_df = df.iloc[cut_idx:]

                print(
                    f"Refined DF starts at: {refined_df.index[0]} | "
                    f"O:{refined_df.iloc[0]['open']} "
                    f"H:{refined_df.iloc[0]['high']} "
                    f"L:{refined_df.iloc[0]['low']} "
                    f"C:{refined_df.iloc[0]['close']}"
                )

                print("🎉 CHOCH CONFIRMED! Plot stays open FOREVER!")
                return refined_df, "BULLISH", t, j, states

    # Only reaches here if NO break
    print("🎬 NO BREAK - no break detected")
    raise ValueError("No break detected")
