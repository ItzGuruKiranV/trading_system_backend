import pandas as pd
from typing import Optional, Dict, List


def plan_trade_from_choch_leg(
    choch_leg_df: pd.DataFrame,
    trend: str,
    pip_value: float = 0.0001,
    displacement_multiplier: float = 1.5,
) -> Optional[Dict]:
    """
    Detect ALL valid OBs inside a 5M CHOCH leg,
    select the execution OB closest to price,
    and plan a mechanical 1:3 trade.
    """
    if choch_leg_df is None or len(choch_leg_df) < 2:
        print("❌ Invalid or too-small 5M leg")
        return None, None

    df = choch_leg_df.copy()
    df = df[["open", "high", "low", "close"]]
    # ======================================================
    # 1️⃣ LEG 50% CALCULATION (NO OB LOGIC)
    # ======================================================
    leg_high = df["high"].max()
    leg_low = df["low"].min()

    mid_price = (leg_high + leg_low) / 2
    leg_start_time = df.index[0]
    leg_end_time = df.index[-1]
    idxs = df.index

    # ======================================================
    # HTF → CHOCH TREND MAPPING
    # ======================================================
    htf_trend = trend.lower()

    if htf_trend == "bullish":
        choch_trend = "bearish"
    else:
        choch_trend = "bullish"
    # ======================================================
    # TRADE PLANNING FROM 50% LEVEL (CHOCH BASED)
    # ======================================================

    if choch_trend == "bullish":
        # Bullish CHOCH → BUY
        entry = mid_price
        stop_loss = leg_low - 4 * pip_value
        risk = entry - stop_loss
        take_profit = entry + 3 * risk
        direction = "BUY"

    else:
        # Bearish CHOCH → SELL
        entry = mid_price
        stop_loss = leg_high + 4 * pip_value
        risk = stop_loss - entry
        take_profit = entry - 3 * risk
        direction = "SELL"

    if risk <= 0:
        print(
            f"[RISK DEBUG] entry={entry}, sl={stop_loss}, risk={risk}"
        )
        print("❌ Invalid risk → Trade skipped\n")
        return None, None
    # ======================================================
    # 3️⃣ FINAL TRADE OBJECT (LEG 50% BASED)
    # ======================================================
    trade = {
        "direction": direction,
        "entry": float(entry),
        "sl": float(stop_loss),
        "tp": float(take_profit),
        "rr": 3.0,
        "htf_trend": htf_trend,
        "choch_trend": choch_trend,
        "leg_high": float(leg_high),
        "leg_low": float(leg_low),
        "mid_price": float(mid_price),
        "leg_start": leg_start_time,
        "leg_end": leg_end_time,
    }

    # ======================================================
    # 4️⃣ PRINT FINAL TRADE
    # ======================================================
    print("====== FINAL TRADE PLAN (50% CHOCH LEG) ======")
    print(f"HTF Trend   : {trade['htf_trend'].upper()}")
    print(f"CHOCH Trend : {trade['choch_trend'].upper()}")
    print(f"Leg Start   : {trade['leg_start']}")
    print(f"Leg End     : {trade['leg_end']}")
    print(f"Leg High    : {trade['leg_high']}")
    print(f"Leg Low     : {trade['leg_low']}")
    print(f"Mid (50%)   : {trade['mid_price']}")
    print(f"Direction   : {trade['direction']}")
    print(f"Entry       : {trade['entry']}")
    print(f"Stop Loss  : {trade['sl']}")
    print(f"Take Profit: {trade['tp']}")
    print(f"Risk-Reward: 1:{trade['rr']}")
    print("=============================================\n")

    return trade, None
