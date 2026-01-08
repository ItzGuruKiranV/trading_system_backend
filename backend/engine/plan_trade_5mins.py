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
        return None

    df = choch_leg_df.copy()
    df = df[["open", "high", "low", "close"]]
    df["range"] = df["high"] - df["low"]

    is_bullish = trend.lower() == "bullish"
    idxs = df.index
    n = len(df)

    # ======================================================
    # 1️⃣ OB SCAN (NO PRINTING YET)
    # ======================================================
    valid_obs: List[Dict] = []

    for i in range(0, n - 1):

        ob_candle = df.iloc[i]
        ob_low = ob_candle["low"]
        ob_high = ob_candle["high"]
        ob_range = ob_candle["range"]

        if ob_range <= 0:
            continue

        next_candle = df.iloc[i + 1]
        next_range = next_candle["range"]

        # Displacement check
        if is_bullish:
            displacement_valid = (
                next_candle["close"] > next_candle["open"]
                and next_range >= displacement_multiplier * ob_range
            )
        else:
            displacement_valid = (
                next_candle["close"] < next_candle["open"]
                and next_range >= displacement_multiplier * ob_range
            )

        if not displacement_valid:
            continue

        # No-break check (OB should not be broken, not just touched)
        future_df = df.iloc[i + 2 :]
        if not future_df.empty:
            # For bullish OB: broken if future low < OB low
            # For bearish OB: broken if future high > OB high
            if is_bullish:
                broken = (future_df["low"] < ob_low).any()
            else:
                broken = (future_df["high"] > ob_high).any()
            
            if broken:
                continue

        valid_obs.append({
            "ob_index": i,
            "ob_time": idxs[i],
            "ob_high": float(ob_high),
            "ob_low": float(ob_low),
        })

    # ======================================================
    # 2️⃣ NO OB CASE
    # ======================================================
    if not valid_obs:
        print("\n❌ No 5M OB found → No trade\n")
        return None

    # ======================================================
    # 3️⃣ PRINT ALL FOUND OBs
    # ======================================================
    print("\n====== 5M ORDER BLOCKS ======")
    for idx, ob in enumerate(valid_obs, 1):
        print(
            f"{idx}. Time: {ob['ob_time']} | "
            f"High: {ob['ob_high']} | Low: {ob['ob_low']}"
        )
    print("=============================\n")

    # ======================================================
    # 4️⃣ SELECT EXECUTION OB
    # ======================================================
    if is_bullish:
        exec_ob = max(valid_obs, key=lambda x: x["ob_high"])
    else:
        exec_ob = min(valid_obs, key=lambda x: x["ob_low"])

    # ======================================================
    # 5️⃣ TRADE PLANNING
    # ======================================================
    first_candle = df.iloc[0]

    if is_bullish:
        stop_loss = first_candle["low"] - 4 * pip_value
        entry = exec_ob["ob_high"]
        risk = entry - stop_loss
        take_profit = entry + 3 * risk
        direction = "BUY"
    else:
        stop_loss = first_candle["high"] + 4 * pip_value
        entry = exec_ob["ob_low"]
        risk = stop_loss - entry
        take_profit = entry - 3 * risk
        direction = "SELL"

    if risk <= 0:
        print("❌ Invalid risk → Trade skipped\n")
        return None

    trade = {
        "direction": direction,
        "entry": float(entry),
        "sl": float(stop_loss),
        "tp": float(take_profit),
        "rr": 3.0,
        "ob_time": exec_ob["ob_time"],
        "ob_high": exec_ob["ob_high"],
        "ob_low": exec_ob["ob_low"],
    }

    # ======================================================
    # 6️⃣ PRINT FINAL TRADE
    # ======================================================
    print("====== FINAL TRADE PLAN ======")
    print(f"Direction   : {trade['direction']}")
    print(f"OB Time     : {trade['ob_time']}")
    print(f"OB High     : {trade['ob_high']}")
    print(f"OB Low      : {trade['ob_low']}")
    print(f"Entry       : {trade['entry']}")
    print(f"Stop Loss  : {trade['sl']}")
    print(f"Take Profit: {trade['tp']}")
    print(f"Risk-Reward: 1:{trade['rr']}")
    print("==============================\n")

    return trade, valid_obs
