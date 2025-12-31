import pandas as pd
import numpy as np
from typing import List, Dict


def detect_pois_from_swing(
    ohlc_df: pd.DataFrame,
    trend: str,
    ob_multiplier: float = 1.5,
    liq_pullback_candles: int = 2,
) -> List[Dict]:
    """
    Unified POI detector (OB + LIQ)
    Timeframe-agnostic, past-data-only, multi-POI capable.
    """

    df = ohlc_df
    df = df[["open", "high", "low", "close"]]
    df["range"] = df["high"] - df["low"]

    is_bull = trend.lower() == "bullish"
    pois: List[Dict] = []

    n = len(df)

    # ======================================================
    # 1️⃣ ORDER BLOCK DETECTION
    # ======================================================
    for i in range(0, n - 2):  # Start from 0 to include first candle
        base = df.iloc[i]
        base_low = base["low"]
        base_high = base["high"]
        base_range = base_high - base_low

        if base_range <= 0:
            continue

        # Need at least one candle after for displacement
        if i + 1 >= n:
            continue
            
        disp = df.iloc[i + 1]
        disp_range = disp["high"] - disp["low"]

        valid_disp = (
            disp["close"] > disp["open"] if is_bull
            else disp["close"] < disp["open"]
        ) and disp_range >= ob_multiplier * base_range

        if not valid_disp:
            continue

        ob_low = base_low
        ob_high = base_high

        # Check if OB is broken (price goes THROUGH it), not just touched
        future = df.iloc[i + 2 :]
        if not future.empty:
            # For bullish OB: broken if future low < OB low
            # For bearish OB: broken if future high > OB high
            if is_bull:
                broken = (future["low"] < ob_low).any()
            else:
                broken = (future["high"] > ob_high).any()
            
            if broken:
                continue

        pois.append({
            "time": df.index[i],
            "type": "OB",
            "trend": trend.upper(),
            "price_low": float(ob_low),
            "price_high": float(ob_high),
        })

    # ======================================================
    # 2️⃣ LIQUIDITY DETECTION
    # ======================================================
    for i in range(1, n - 1):
        protected = df["high"].iloc[i] if is_bull else df["low"].iloc[i]

        if (
            df["high"].iloc[i + 1] > protected
            if is_bull
            else df["low"].iloc[i + 1] < protected
        ):
            continue

        pb = 0
        j = i + 1
        while j < n and (
            df["close"].iloc[j] < df["open"].iloc[j]
            if is_bull
            else df["close"].iloc[j] > df["open"].iloc[j]
        ):
            pb += 1
            j += 1

        if pb < liq_pullback_candles:
            continue

        k = j
        while k < n and not (
            df["high"].iloc[k] > protected
            if is_bull
            else df["low"].iloc[k] < protected
        ):
            k += 1

        if k == n:
            continue

        region = (
            df["low"].iloc[i : k + 1]
            if is_bull
            else df["high"].iloc[i : k + 1]
        )

        liq_low = region.min()
        liq_high = region.max()

        future = df.iloc[k + 1 :]
        tapped = (
            (future["low"] <= liq_high) &
            (future["high"] >= liq_low)
        ).any()

        if tapped:
            continue

        pois.append({
            "time": df.index[i],
            "type": "LIQ",
            "trend": trend.upper(),
            "price_low": float(liq_low) if is_bull else None,
            "price_high": float(liq_high) if not is_bull else None,
        })

    # ======================================================
    # 🖨️ PRINT ALL POIs (OB + LIQ)
    # ======================================================
    print("\n========== POIs DETECTED ==========")
    if not pois:
        print("None")
    else:
        for idx, p in enumerate(pois, 1):
            if p["type"] == "OB":
                print(
                    f"{idx}. {p['trend']} OB | "
                    f"LOW: {p['price_low']} | HIGH: {p['price_high']}"
                )
            else:
                side = "LOW" if p["price_low"] is not None else "HIGH"
                price = p["price_low"] if p["price_low"] is not None else p["price_high"]
                print(
                    f"{idx}. {p['trend']} LIQ | "
                    f"{side}: {price}"
                )
    print("=================================\n")

    return pois
