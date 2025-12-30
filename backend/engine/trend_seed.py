import pandas as pd
import sys
import os
import matplotlib.pyplot as plt  # ← ADD THIS
import matplotlib  # ← ADD THIS

# Fix debug folder path
debug_path = os.path.join(os.path.dirname(__file__), '..', 'debug')
sys.path.insert(0, debug_path)

from seed_plot import SeedPlotter  

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
    """
    DYNAMIC REAL-TIME SEED DETECTION WITH INSTANT PLOTTING!
    Plots EXACTLY when BOS/CHOCH/PULLBACK events happen.
    """
    df = df_4h.copy().sort_index()

    if len(df) < SEED_CANDLES + 5:
        raise ValueError("Not enough data for seed detection")

    plotter = SeedPlotter(df, [])
    plotter.states = []  # Track states for plotting past events
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

    # DYNAMIC: Plot seed candles ONE BY ONE
    for i in range(SEED_CANDLES):
        seed_complete = (i == SEED_CANDLES - 1)  # ← LAST seed candle
        state=CandleState(
            index=i, time=df.index[i], temp_trend=temp_trend,
            pullback_active=False, protected_level=None,
            seed_high=seed_high, seed_low=seed_low,
            seed_complete=seed_complete
        )
        states.append(state)
        plotter.states.append(state)
        plotter.plot_single_state(state)    


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
        plotter.states.append(state)

        

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
                    plotter.plot_single_state(state)
                    continue
                
                # protected high must NOT break
                if pullback_active:
                    if candle["high"] > protected_level:
                        # 🔥 PULLBACK RESET → PLOT!
                        state.event = "PULLBACK_RESET"
                        pullback_active = False
                        protected_level = None
                        pullback_lows.clear()
                        pullback_highs.clear()
                        plotter.plot_single_state(state)
                        continue
                    else:
                        pullback_lows.append(candle["low"])
                        pullback_highs.append(candle["high"])

            if pullback_active and len(pullback_lows) >= 1:
                # 🔥 PULLBACK CONFIRMED → PLOT!
                final_pullback_low = min(pullback_lows)
                final_pullback_high = max(pullback_highs)
                state.pullback_low = final_pullback_low
                state.pullback_high = final_pullback_high
                state.event = "PULLBACK_CONFIRMED"
                pullback_confirm_idx = i
                plotter.plot_single_state(state)
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
                # 🔥 PULLBACK START → PLOT!
                protected_level = prev_candle["low"]
                pullback_start_idx = i
                pullback_active = True
                state.event = "PULLBACK_START"
                plotter.plot_single_state(state)
                continue

            if pullback_active:
                if candle["low"] < protected_level:
                    # 🔥 PULLBACK RESET → PLOT!
                    state.event = "PULLBACK_RESET"
                    pullback_active = False
                    protected_level = None
                    pullback_lows.clear()
                    pullback_highs.clear()
                    plotter.plot_single_state(state)
                    continue
                else:
                    pullback_lows.append(candle["low"])
                    pullback_highs.append(candle["high"])

            if pullback_active and len(pullback_highs) >= 1:
                # 🔥 PULLBACK CONFIRMED → PLOT!
                final_pullback_low = min(pullback_lows)
                final_pullback_high = max(pullback_highs)
                state.pullback_low = final_pullback_low
                state.pullback_high = final_pullback_high
                state.event = "PULLBACK_CONFIRMED"
                pullback_confirm_idx = i
                plotter.plot_single_state(state)
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
        plotter.states.append(state)

        if temp_trend == "BULLISH":
            if candle["high"] > seed_high:
                print(f"BOS ↑ at {t}")
                state.event = "BOS"
                plotter.plot_single_state(state)
                refined_df = df[df.index >= df.index[pullback_confirm_idx]]
                
                # 🔥 KEEP OPEN AFTER BOS!
                print("🎉 BOS CONFIRMED! Plot stays open FOREVER!")
                print("📊 Close window → continues to Market Structure phase")
                plt.ioff()
                plt.show(block=True)
                return refined_df, "BULLISH", t, j, states
            
            if candle["low"] < seed_low:
                print(f"CHOCH ↓ at {t}")
                state.event = "CHOCH"
                plotter.plot_single_state(state)
                refined_df = df[df.index >= df.index[pullback_confirm_idx]]
                
                print("🎉 CHOCH CONFIRMED! Plot stays open FOREVER!")
                print("📊 Close window → continues...")
                plt.ioff()
                plt.show(block=True)
                return refined_df, "BEARISH", t, j, states
        
        else:  # BEARISH
            if candle["low"] < seed_low:
                print(f"BOS ↓ at {t}")
                state.event = "BOS"
                plotter.plot_single_state(state)
                refined_df = df[df.index >= df.index[pullback_confirm_idx]]
                
                print("🎉 BOS CONFIRMED! Plot stays open FOREVER!")
                plt.ioff()
                plt.show(block=True)
                return refined_df, "BEARISH", t, j, states
            
            if candle["high"] > seed_high:
                print(f"CHOCH ↑ at {t}")
                state.event = "CHOCH"
                plotter.plot_single_state(state)
                refined_df = df[df.index >= df.index[pullback_confirm_idx]]
                
                print("🎉 CHOCH CONFIRMED! Plot stays open FOREVER!")
                plt.ioff()
                plt.show(block=True)
                return refined_df, "BULLISH", t, j, states

    # Only reaches here if NO break
    print("🎬 NO BREAK - Plot stays open...")
    plt.ioff()
    plt.show(block=True)
    raise ValueError("No break detected")
