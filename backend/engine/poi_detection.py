import pandas as pd
from typing import List, Dict
import plotly.graph_objects as go
from datetime import datetime


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

    # print(f"Sorted {len(bull_sorted)} bullish POIs and {len(bear_sorted)} bearish POIs.")
    return bull_sorted + bear_sorted


# # ======================================================
# # 🔧 TEMP DEBUG PLOTTING FUNCTION (HTML)
# # ======================================================
# def plot_pois_debug(df: pd.DataFrame, pois: List[Dict], trend: str):
#     fig = go.Figure()

#     # Candles
#     fig.add_trace(go.Candlestick(
#         x=df.index,
#         open=df["open"],
#         high=df["high"],
#         low=df["low"],
#         close=df["close"],
#         name="Price"
#     ))

#     # POIs
#     for p in pois:
#         if p["type"] == "OB":
#             fig.add_shape(
#                 type="rect",
#                 x0=p["time"],
#                 x1=df.index[-1],
#                 y0=p["price_low"],
#                 y1=p["price_high"],
#                 fillcolor="rgba(0, 200, 0, 0.25)" if p["trend"] == "BULLISH" else "rgba(200, 0, 0, 0.25)",
#                 line_width=0,
#                 layer="below"
#             )

#         elif p["type"] == "LIQ":
#             y = p["price_low"] if p["trend"] == "BULLISH" else p["price_high"]
#             fig.add_shape(
#                 type="line",
#                 x0=p["time"],
#                 x1=df.index[-1],
#                 y0=y,
#                 y1=y,
#                 line=dict(color="blue", width=2, dash="dash")
#             )

#     fig.update_layout(
#         title=f"POI Debug Plot — {trend}",
#         xaxis_title="Time",
#         yaxis_title="Price",
#         xaxis_rangeslider_visible=False,
#         template="plotly_dark",
#         height=700
#     )

#     fname = f"pois_debug_{trend.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
#     fig.write_html(fname)
#     print(f"📊 POI debug plot saved: {fname}")


# ======================================================
# 🧠 POI DETECTION LOGIC
# ======================================================
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
    # 1️⃣ ORDER BLOCK DETECTION
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
    # 🔧 OB MERGING
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
    # 2️⃣ LIQUIDITY DETECTION (DEBUG VERSION)
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
                old = temp_high
                temp_high = max(temp_high, candle["high"])
                # if temp_high != old:
                #     print(f"📈 Updated temp_high → {temp_high}")
            else:
                old = temp_low
                temp_low = min(temp_low, candle["low"])
                # if temp_low != old:
                #     print(f"📉 Updated temp_low → {temp_low}")

        # --------------------------
        # PULLBACK DETECTION
        # --------------------------
        is_pullback = (
            (candle["close"] < candle["open"]) if is_bull
            else (candle["close"] > candle["open"])
        )

        # print(f"↩️ Pullback candle? {is_pullback}")

        if is_pullback:
            if prev_pb_high is not None:
                if is_bull and candle["high"] > prev_pb_high:
                    # print("❌ Pullback INVALIDATED (higher high in bullish PB)")
                    pullback_indices = []
                    in_pullback = False
                    prev_pb_high = prev_pb_low = None
                    i += 1
                    continue

                if not is_bull and candle["low"] < prev_pb_low:
                    # print("❌ Pullback INVALIDATED (lower low in bearish PB)")
                    pullback_indices = []
                    in_pullback = False
                    prev_pb_high = prev_pb_low = None
                    i += 1
                    continue

            pullback_indices.append(i)
            in_pullback = True
            prev_pb_high = candle["high"]
            prev_pb_low = candle["low"]

            # print(f"✅ Pullback accepted | PB candles = {len(pullback_indices)}")

        # --------------------------
        # WAIT FOR BOS
        # --------------------------
        if in_pullback and len(pullback_indices) >= liq_pullback_candles:
            zone_low = df.iloc[pullback_indices]["low"].min()
            zone_high = df.iloc[pullback_indices]["high"].max()

            # print(f"⏳ Waiting for BOS | Zone low={zone_low}, high={zone_high}")

            k = i + 1
            while k < n:
                curr = df.iloc[k]

                # print(f"   🔎 Checking BOS at candle {k} "
                #     f"(H={curr['high']} L={curr['low']})")

                if is_bull and curr["high"] > temp_high:
                    liq_price = zone_low
                    # print(f"🔥 BOS CONFIRMED (bullish) at {k}, LIQ price={liq_price}")
                    temp_high = curr["high"]
                    break

                if not is_bull and curr["low"] < temp_low:
                    liq_price = zone_high
                    # print(f"🔥 BOS CONFIRMED (bearish) at {k}, LIQ price={liq_price}")
                    temp_low = curr["low"]
                    break

                zone_low = min(zone_low, curr["low"])
                zone_high = max(zone_high, curr["high"])
                k += 1
            else:
                # print("❌ BOS never happened — reset pullback")
                pullback_indices = []
                in_pullback = False
                prev_pb_high = prev_pb_low = None
                i += 1
                continue

            # --------------------------
            # TAPPED CHECK
            # --------------------------
            future = df.iloc[k + 1:]
            if not future.empty:
                tapped = (
                    (future["low"] <= liq_price).any()
                    if is_bull
                    else (future["high"] >= liq_price).any()
                )

                # print(f"👀 Future tap check → tapped={tapped}")

                if tapped:
                    # print("❌ LIQ REJECTED (tapped later)")
                    pullback_indices = []
                    in_pullback = False
                    prev_pb_high = prev_pb_low = None
                    i = k + 1
                    continue

            # print("✅ LIQ ACCEPTED & STORED")

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
    print(f"Detected {len(merged_obs)} OBs and {len(liqs)} LIQs for {trend} trend.")

    # 🔥 TEMP HTML DEBUG
    # plot_pois_debug(df, pois, trend)

    return sort_pois_merged(pois)
