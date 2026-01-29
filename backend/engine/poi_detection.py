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


# ======================================================
# 🔧 TEMP DEBUG PLOTTING FUNCTION (HTML)
# ======================================================
def plot_pois_debug(df: pd.DataFrame, pois: List[Dict], trend: str):
    fig = go.Figure()

    # Candles
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Price"
    ))

    # POIs
    for p in pois:
        if p["type"] == "OB":
            fig.add_shape(
                type="rect",
                x0=p["time"],
                x1=df.index[-1],
                y0=p["price_low"],
                y1=p["price_high"],
                fillcolor="rgba(0, 200, 0, 0.25)" if p["trend"] == "BULLISH" else "rgba(200, 0, 0, 0.25)",
                line_width=0,
                layer="below"
            )

        elif p["type"] == "LIQ":
            y = p["price_low"] if p["trend"] == "BULLISH" else p["price_high"]
            fig.add_shape(
                type="line",
                x0=p["time"],
                x1=df.index[-1],
                y0=y,
                y1=y,
                line=dict(color="blue", width=2, dash="dash")
            )

    fig.update_layout(
        title=f"POI Debug Plot — {trend}",
        xaxis_title="Time",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=700
    )

    fname = f"pois_debug_{trend.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    fig.write_html(fname)
    print(f"📊 POI debug plot saved: {fname}")


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
    # 2️⃣ LIQUIDITY DETECTION (SIMPLE & CLEAN)
    # ======================================================

    temp_high = df.iloc[0]["high"]
    temp_low  = df.iloc[0]["low"]

    pullback_count = 0
    liq_buffer_indices = []

    i = 1
    while i < n:
        candle = df.iloc[i]

        # ==========================
        # 🔼 BULLISH TREND
        # ==========================
        if is_bull:

            # --------------------------
            # Price still inside structure
            # --------------------------
            if candle["high"] < temp_high:
                liq_buffer_indices.append(i)

                # bearish candle = pullback
                if candle["close"] < candle["open"]:
                    pullback_count += 1

            # --------------------------
            # BOS after pullback → LIQ
            # --------------------------
            elif pullback_count >= liq_pullback_candles and candle["high"] > temp_high:
                buffer_df = df.iloc[liq_buffer_indices]
                liq_price = buffer_df["low"].min()

                # 🔎 future tap check
                future = df.iloc[i + 1:]
                tapped = (future["low"] <= liq_price).any() if not future.empty else False

                if not tapped:
                    liqs.append({
                        "time": df.index[i],
                        "type": "LIQ",
                        "trend": trend.upper(),
                        "price_low": float(liq_price),
                        "price_high": None,
                        "if_valid": True,
                    })

                # ✅ RESET after BOS
                temp_high = candle["high"]
                pullback_count = 0
                liq_buffer_indices = []

            # --------------------------
            # Direct impulse continuation
            # --------------------------
            elif candle["high"] > temp_high:
                temp_high = candle["high"]
                pullback_count = 0
                liq_buffer_indices = []

        # ==========================
        # 🔽 BEARISH TREND (MIRROR)
        # ==========================
        else:

            # --------------------------
            # Price still inside structure
            # --------------------------
            if candle["low"] > temp_low:
                liq_buffer_indices.append(i)

                # bullish candle = pullback
                if candle["close"] > candle["open"]:
                    pullback_count += 1

            # --------------------------
            # BOS after pullback → LIQ
            # --------------------------
            elif pullback_count >= liq_pullback_candles and candle["low"] < temp_low:
                buffer_df = df.iloc[liq_buffer_indices]
                liq_price = buffer_df["high"].max()

                # 🔎 future tap check
                future = df.iloc[i + 1:]
                tapped = (future["high"] >= liq_price).any() if not future.empty else False

                if not tapped:
                    liqs.append({
                        "time": df.index[i],
                        "type": "LIQ",
                        "trend": trend.upper(),
                        "price_low": None,
                        "price_high": float(liq_price),
                        "if_valid": True,
                    })

                # ✅ RESET after BOS
                temp_low = candle["low"]
                pullback_count = 0
                liq_buffer_indices = []

            # --------------------------
            # Direct impulse continuation
            # --------------------------
            elif candle["low"] < temp_low:
                temp_low = candle["low"]
                pullback_count = 0
                liq_buffer_indices = []

        i += 1


    pois = merged_obs + liqs
    print(f"Detected {len(merged_obs)} OBs and {len(liqs)} LIQs for {trend} trend.")

    #plot_pois_debug(df, pois, trend)
    return sort_pois_merged(pois)



