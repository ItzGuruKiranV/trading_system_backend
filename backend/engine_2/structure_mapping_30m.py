import pandas as pd
from typing import Optional, Dict

from engine_2.poi_detection_30m import detect_pois_from_swing
from engine_2.structure_30m import process_structure_and_return_last_swing
from engine_2.choch_30m import process_structure_and_return_last_swing
from engine_2.main_engine import engine_30m 

def market_structure_mapping_30m(
    df_4h: pd.DataFrame,
    df_5m: pd.DataFrame,
    df_30m: pd.DataFrame,
    trend: str,
    bos_time,
    pullback_pct: float = 0.35,
    min_pullback_candles: int = 5,
    depth: int = 0,
    max_depth: int = 50,
) -> Dict:
    """
    ENGINE-2 : 30M STRUCTURE DRIVER

    Responsibility:
    - Validate HTF pullback
    - Detect POIs
    - Monitor 30M candles candle-by-candle
    - Priority:
        1) HTF CHOCH
        2) HTF BOS
        3) POI invalidation
        4) POI tap → 30M structure
    """

    indent = "    " * depth
    trend = trend.upper()

    print(f"\n{indent}🚀 ENGINE-2 (30M) START")

    # --------------------------------------------------
    # SAFETY
    # --------------------------------------------------
    if depth >= max_depth:
        return {"status": "MAX_DEPTH"}

    if len(df_4h) < 5:
        return {"status": "INSUFFICIENT_4H"}

    # --------------------------------------------------
    # INITIAL PROTECTED SWING
    # --------------------------------------------------
    first_4h = df_4h.iloc[0]

    if trend == "BULLISH":
        swing_low = first_4h.low
        swing_high = None
    else:
        swing_high = first_4h.high
        swing_low = None

    print(f"{indent}🔒 Protected HTF swing locked")

    # --------------------------------------------------
    # 4H PULLBACK VALIDATION
    # --------------------------------------------------
    candidate_high = None
    candidate_low = None
    pullback_time = None

    bearish_count = 0
    bullish_count = 0

    pullback_df = df_4h[df_4h.index >= bos_time]

    for t, c in pullback_df.iterrows():

        if trend == "BULLISH":

            if candidate_high is None or c.high > candidate_high:
                candidate_high = c.high
                bearish_count = 0
                continue

            if c.close < c.open:
                bearish_count += 1

            depth_valid = (
                (candidate_high - c.low)
                / max(candidate_high - swing_low, 1e-9)
            ) >= pullback_pct

            if bearish_count >= min_pullback_candles or depth_valid:
                pullback_time = t
                swing_high = candidate_high
                break

        else:

            if candidate_low is None or c.low < candidate_low:
                candidate_low = c.low
                bullish_count = 0
                continue

            if c.close > c.open:
                bullish_count += 1

            depth_valid = (
                (c.high - candidate_low)
                / max(swing_high - candidate_low, 1e-9)
            ) >= pullback_pct

            if bullish_count >= min_pullback_candles or depth_valid:
                pullback_time = t
                swing_low = candidate_low
                break

    if pullback_time is None:
        return {"status": "NO_PULLBACK"}

    print(f"{indent}✅ Pullback confirmed @ {pullback_time}")

    # --------------------------------------------------
    # POI DETECTION (4H LEG)
    # --------------------------------------------------
    swing_df = df_4h.loc[:pullback_time]

    pois = detect_pois_from_swing(
        ohlc_df=swing_df,
        trend=trend,
    )

    print(f"{indent}🎯 POIs detected: {len(pois)}")

    if not pois:
        return {"status": "NO_POI"}

    # --------------------------------------------------
    # POST-PULLBACK DATA
    # --------------------------------------------------
    df_30m_post = df_30m[df_30m.index > pullback_time]

    poi_index = 0
    poi_active = False
    protected_30m_point = None

    i = 0

    # ==================================================
    # MAIN REAL-TIME LOOP (30M)
    # ==================================================
    while i < len(df_30m_post):

        t30 = df_30m_post.index[i]
        c30 = df_30m_post.iloc[i]

        # ==================================================
        # 1️⃣ HTF CHOCH (ABSOLUTE PRIORITY)
        # ==================================================
        if trend == "BULLISH" and c30.close < swing_low:
            print(f"{indent}🟥 HTF CHOCH @ {t30}")
            return {
                "status": "HTF_CHOCH",
                "time": t30,
                "new_trend": "BEARISH",
                "df_4h": df_4h[df_4h.index >= t30],
                "df_5m": df_5m[df_5m.index >= t30],
                "df_30m": df_30m[df_30m.index >= t30],
            }

        if trend == "BEARISH" and c30.close > swing_high:
            print(f"{indent}🟥 HTF CHOCH @ {t30}")
            return {
                "status": "HTF_CHOCH",
                "time": t30,
                "new_trend": "BULLISH",
                "df_4h": df_4h[df_4h.index >= t30],
                "df_5m": df_5m[df_5m.index >= t30],
                "df_30m": df_30m[df_30m.index >= t30],
            }

        # ==================================================
        # 2️⃣ HTF BOS (CONTINUATION)
        # ==================================================
        if trend == "BULLISH" and c30.close > swing_high:
            print(f"{indent}🟦 HTF BOS @ {t30}")
            return {
                "status": "HTF_BOS",
                "time": t30,
                "trend": trend,
                "df_4h": df_4h[df_4h.index >= t30],
                "df_5m": df_5m[df_5m.index >= t30],
                "df_30m": df_30m[df_30m.index >= t30],
            }

        if trend == "BEARISH" and c30.close < swing_low:
            print(f"{indent}🟦 HTF BOS @ {t30}")
            return {
                "status": "HTF_BOS",
                "time": t30,
                "trend": trend,
                "df_4h": df_4h[df_4h.index >= t30],
                "df_5m": df_5m[df_5m.index >= t30],
                "df_30m": df_30m[df_30m.index >= t30],
            }

        # ==================================================
        # 3️⃣ POI LOGIC
        # ==================================================
        if poi_index >= len(pois):
            i += 1
            continue

        active_poi = pois[poi_index]
        poi_type = active_poi["type"]
        poi_low = active_poi["price_low"]
        poi_high = active_poi["price_high"]

        # --------------------------------------------------
        # POI TAP
        # --------------------------------------------------
        if not poi_active:

            tapped = False

            if trend == "BULLISH":
                if poi_type == "OB" and c30.low <= poi_high:
                    tapped = True
                if poi_type == "LIQ" and c30.low <= poi_low:
                    tapped = True
            else:
                if poi_type == "OB" and c30.high >= poi_low:
                    tapped = True
                if poi_type == "LIQ" and c30.high >= poi_high:
                    tapped = True

            if tapped:
                print(f"{indent}🔥 POI TAPPED ({poi_type}) @ {t30}")
                poi_active = True

                opp_trend = "BEARISH" if trend == "BULLISH" else "BULLISH"

                m30_slice = df_30m.loc[pullback_time:t30]

                protected_30m_point = process_structure_and_return_last_swing(
                    df=m30_slice,
                    trend=opp_trend,
                )

                if protected_30m_point is None:
                    print(f"{indent}❌ Invalid 30M structure → next POI")
                    poi_active = False
                    poi_index += 1

        # --------------------------------------------------
        # 30M STRUCTURE CHECK (CHOCH)
        # --------------------------------------------------
        elif protected_30m_point is not None:

            # =========================
            # 30M CHOCH DETECTED
            # =========================
            if trend == "BULLISH" and c30.close < protected_30m_point:
                print(f"{indent}🎯 30M CHOCH @ {t30}")

                choch_level = c30.low

                engine_30m_result = engine_30m(
                    df_30m=df_30m[df_30m.index >= t30],
                    df_5m=df_5m[df_5m.index >= t30],
                    trend=trend,
                    choch_time=t30,
                    choch_level=choch_level,
                    htf_swing_high=swing_high,
                    htf_swing_low=swing_low,
                    poi=active_poi,
                )

            elif trend == "BEARISH" and c30.close > protected_30m_point:
                print(f"{indent}🎯 30M CHOCH @ {t30}")

                choch_level = c30.high

                engine_30m_result = engine_30m(
                    df_30m=df_30m[df_30m.index >= t30],
                    df_5m=df_5m[df_5m.index >= t30],
                    trend=trend,
                    choch_time=t30,
                    choch_level=choch_level,
                    htf_swing_high=swing_high,
                    htf_swing_low=swing_low,
                    poi=active_poi,
                )

            else:
                engine_30m_result = None



        i += 1

    return {"status": "CONTINUE"}
