import pandas as pd
from typing import List, Dict


def detect_pois_from_swing(
    ohlc_df: pd.DataFrame,
    trend: str,
    ob_multiplier: float = 1.8,
    liq_pullback_candles: int = 2,
) -> List[Dict]:

    df = ohlc_df[["open", "high", "low", "close"]].copy()
    df["range"] = df["high"] - df["low"]

    is_bull = trend.lower() == "bullish"
    pois: List[Dict] = []
    n = len(df)

    # ======================================================
    # 1️⃣ INSTITUTIONAL ORDER BLOCK DETECTION (UNCHANGED)
    # ======================================================
    for i in range(3, n - 3):

        disp_window = df.iloc[i:i+3]
        disp_high = disp_window["high"].max()
        disp_low = disp_window["low"].min()
        disp_range = disp_high - disp_low

        prev_ranges = df["range"].iloc[i-5:i]
        avg_prev_range = prev_ranges.mean()

        if avg_prev_range <= 0:
            continue

        closes = disp_window["close"]
        opens = disp_window["open"]

        direction_ok = (
            (closes > opens).sum() >= 2 if is_bull
            else (closes < opens).sum() >= 2
        )

        if not direction_ok:
            continue

        if disp_range < ob_multiplier * avg_prev_range:
            continue

        lookback = df.iloc[i-10:i]
        if lookback.empty:
            continue

        if is_bull:
            if disp_high <= lookback["high"].max():
                continue
        else:
            if disp_low >= lookback["low"].min():
                continue

        for lb in [3, 2, 1]:
            base = df.iloc[i-lb:i]
            base_low = base["low"].min()
            base_high = base["high"].max()
            base_range = base_high - base_low

            if base_range <= 0:
                continue

            if base_range > 0.30 * disp_range:
                continue

            if is_bull:
                if not (base["close"] < base["open"]).any():
                    continue
            else:
                if not (base["close"] > base["open"]).any():
                    continue

            future = df.iloc[i+3:]
            if not future.empty:
                if is_bull and (future["low"] < base_low).any():
                    continue
                if not is_bull and (future["high"] > base_high).any():
                    continue

            pois.append({
                "time": df.index[i-lb],
                "type": "OB",
                "trend": trend.upper(),
                "price_low": float(base_low),
                "price_high": float(base_high),
            })
            break

    # ======================================================
    # 🔧 OB MERGING LOGIC (NEW – ONLY REFINEMENT)
    # ======================================================
    obs = [p for p in pois if p["type"] == "OB"]
    liqs = [p for p in pois if p["type"] == "LIQ"]

    obs.sort(key=lambda x: x["time"])
    merged_obs: List[Dict] = []

    for ob in obs:
        if not merged_obs:
            merged_obs.append(ob)
            continue

        last = merged_obs[-1]

        overlap = not (
            ob["price_high"] < last["price_low"]
            or ob["price_low"] > last["price_high"]
        )

        if overlap:
            last["price_low"] = min(last["price_low"], ob["price_low"])
            last["price_high"] = max(last["price_high"], ob["price_high"])
            last["time"] = min(last["time"], ob["time"])
        else:
            merged_obs.append(ob)

    # ======================================================
    # 2️⃣ INSTITUTIONAL LIQUIDITY DETECTION (UNCHANGED)
    # ======================================================
    for i in range(liq_pullback_candles, n - 1):

        pullback = df.iloc[i - liq_pullback_candles:i]

        if is_bull:
            if not (pullback["close"] < pullback["open"]).all():
                continue
        else:
            if not (pullback["close"] > pullback["open"]).all():
                continue

        prior_df = df.iloc[:i - liq_pullback_candles]
        if prior_df.empty:
            continue

        if is_bull:
            swing_extreme = prior_df["low"].min()
            pb_extreme = pullback["high"].max()
            retrace_level = swing_extreme + 0.5 * (pb_extreme - swing_extreme)
        else:
            swing_extreme = prior_df["high"].max()
            pb_extreme = pullback["low"].min()
            retrace_level = swing_extreme - 0.5 * (swing_extreme - pb_extreme)

        curr = df.iloc[i]

        if is_bull:
            if curr["low"] > retrace_level:
                continue
            liq_price = swing_extreme
        else:
            if curr["high"] < retrace_level:
                continue
            liq_price = swing_extreme

        future = df.iloc[i + 1:]
        if not future.empty:
            tapped = (
                (future["low"] <= liq_price).any()
                if is_bull
                else (future["high"] >= liq_price).any()
            )
            if tapped:
                continue

        liqs.append({
            "time": df.index[i - 1],
            "type": "LIQ",
            "trend": trend.upper(),
            "price_low": float(liq_price) if is_bull else None,
            "price_high": float(liq_price) if not is_bull else None,
        })

    # ======================================================
    # FINAL OUTPUT
    # ======================================================
    pois = merged_obs + liqs
    return pois