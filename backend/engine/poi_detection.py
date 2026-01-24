import pandas as pd
from typing import List, Dict

price_low = None
price_high = None

def sort_pois_merged(pois):
    def bull_key(p):
        if p['type'] == 'OB':
            return p['price_high']
        elif p['type'] == 'LIQ':
            return p['price_low']
        return 0

    def bear_key(p):
        if p['type'] == 'OB':
            return p['price_low']
        elif p['type'] == 'LIQ':
            return p['price_high'] if p['price_high'] is not None else float('inf')
        return 0

    bull_pois = [p for p in pois if p['trend'] == 'BULLISH']
    bear_pois = [p for p in pois if p['trend'] == 'BEARISH']

    bull_sorted = sorted(bull_pois, key=bull_key, reverse=True)
    bear_sorted = sorted(bear_pois, key=bear_key)

    return bull_sorted + bear_sorted


def detect_pois_from_swing(
    ohlc_df: pd.DataFrame,
    trend: str,
    ob_multiplier: float = 1.8,
    liq_pullback_candles: int = 4,
) -> List[Dict]:

    df = ohlc_df[["open", "high", "low", "close"]].copy()
    df["range"] = df["high"] - df["low"]

    is_bull = trend.lower() == "bullish"
    pois: List[Dict] = []
    n = len(df)

    # ======================================================
    # 1️⃣ INSTITUTIONAL ORDER BLOCK DETECTION (UNCHANGED)
    # ======================================================
    for i in range(0, n - 2):
        next_candle = df.iloc[i + 1]

        closes = next_candle["close"]
        opens = next_candle["open"]

        disp_range = (closes - opens) if is_bull else (opens - closes)

        direction_ok = (closes > opens) if is_bull else (closes < opens)
        if not direction_ok:
            continue

        base = df.iloc[i]

        if is_bull and base["close"] >= base["open"]:
            continue
        if not is_bull and base["close"] <= base["open"]:
            continue

        base_low = base["low"]
        base_high = base["high"]
        base_range = base_high - base_low

        if base_range <= 0 or disp_range < ob_multiplier * base_range:
            continue

        future = df.iloc[i + 2:]
        if not future.empty:
            if is_bull and (future["low"] < base_high).any():
                continue
            if not is_bull and (future["high"] > base_low).any():
                continue

        if is_bull:
            price_low = min(base_low, next_candle["low"])
            price_high = base_high
        else:
            price_low = base_low
            price_high = max(base_high, next_candle["high"])

        pois.append({
            "time": df.index[i],
            "type": "OB",
            "trend": trend.upper(),
            "price_low": float(price_low),
            "price_high": float(price_high),
            "if_valid": True,
        })

    # ======================================================
    # 🔧 OB MERGING LOGIC (UNCHANGED)
    # ======================================================
    obs = [p for p in pois if p["type"] == "OB"]
    liqs = []

    obs.sort(key=lambda x: x["time"])
    merged_obs = []

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
    # 2️⃣ INSTITUTIONAL LIQUIDITY DETECTION (WITH YOUR RULE)
    # ======================================================
    temp_high = df.iloc[0]["high"]
    temp_low = df.iloc[0]["low"]

    pullback_indices = []
    in_pullback = False
    prev_pb_high = None
    prev_pb_low = None

    i = 1
    while i < n:

        candle = df.iloc[i]

        # --------------------------
        # IMPULSE UPDATE
        # --------------------------
        if not in_pullback:
            if is_bull:
                temp_high = max(temp_high, candle["high"])
            else:
                temp_low = min(temp_low, candle["low"])

        # --------------------------
        # PULLBACK CANDLE DETECTION
        # --------------------------
        is_pullback = (
            (candle["close"] < candle["open"]) if is_bull
            else (candle["close"] > candle["open"])
        )

        if is_pullback:

            # 🔒 YOUR STRUCTURAL RULE
            if prev_pb_high is not None:
                if is_bull and candle["high"] > prev_pb_high:
                    pullback_indices = []
                    in_pullback = False
                    prev_pb_high = prev_pb_low = None
                    i += 1
                    continue

                if not is_bull and candle["low"] < prev_pb_low:
                    pullback_indices = []
                    in_pullback = False
                    prev_pb_high = prev_pb_low = None
                    i += 1
                    continue

            pullback_indices.append(i)
            in_pullback = True
            prev_pb_high = candle["high"]
            prev_pb_low = candle["low"]

        # --------------------------
        # WAIT FOR BOS
        # --------------------------
        if in_pullback and len(pullback_indices) >= liq_pullback_candles:

            zone_low = df.iloc[pullback_indices]["low"].min()
            zone_high = df.iloc[pullback_indices]["high"].max()

            k = i + 1
            while k < n:
                curr = df.iloc[k]

                if is_bull and curr["high"] > temp_high:
                    liq_price = zone_low
                    break

                if not is_bull and curr["low"] < temp_low:
                    liq_price = zone_high
                    break

                zone_low = min(zone_low, curr["low"])
                zone_high = max(zone_high, curr["high"])
                k += 1
            else:
                pullback_indices = []
                in_pullback = False
                prev_pb_high = prev_pb_low = None
                i += 1
                continue

            future = df.iloc[k + 1:]
            if not future.empty:
                tapped = (
                    (future["low"] <= liq_price).any()
                    if is_bull
                    else (future["high"] >= liq_price).any()
                )
                if tapped:
                    pullback_indices = []
                    in_pullback = False
                    prev_pb_high = prev_pb_low = None
                    i = k + 1
                    continue

            liqs.append({
                "time": df.index[pullback_indices[-1]],
                "type": "LIQ",
                "trend": trend.upper(),
                "price_low": float(liq_price) if is_bull else None,
                "price_high": float(liq_price) if not is_bull else None,
                "if_valid": True,
            })

            pullback_indices = []
            in_pullback = False
            prev_pb_high = prev_pb_low = None
            i = k + 1
            continue

        i += 1

    pois = merged_obs + liqs
    return sort_pois_merged(pois)