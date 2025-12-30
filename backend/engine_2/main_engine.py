import pandas as pd
from typing import Dict, Optional

from engine_2.poi_detection_30m import detect_pois_from_swing
from engine.mins_choch import process_structure_and_return_last_swing
from engine.plan_trade_5mins import plan_trade_from_choch_leg


def engine_30m_beast_realtime(
    df_30m: pd.DataFrame,
    df_5m: pd.DataFrame,
    trend: str,
    htf_swing_high: float,
    htf_swing_low: float,
    pullback_pct: float = 0.35,
    min_pullback_candles: int = 2,
) -> Dict:

    trend = trend.upper()

    # ===============================
    # STATE (30M)
    # ===============================
    pullback_confirmed = False
    pullback_time = None

    impulse_high: Optional[float] = None
    impulse_low: Optional[float] = None
    opp_count = 0

    choch_level_30m: Optional[float] = None

    pois = []
    poi_index = 0

    # Trade state
    trade_taken = False
    trade_details: Optional[dict] = None
    entry_filled = False

    # BOS tracking (kept as in your code)
    bos_confirmed = False
    bos_range_low: Optional[float] = None

    # ===============================
    # MAIN 30M LOOP
    # ===============================
    for t30, c30 in df_30m.iterrows():

        # --------------------------------------------------
        # 1️⃣ 4H BOS (HARD EXIT)
        # --------------------------------------------------
        if trend == "BULLISH" and c30.close > htf_swing_high:
            return {"status": 1, "time": t30}

        if trend == "BEARISH" and c30.close < htf_swing_low:
            return {"status": 1, "time": t30}

        # --------------------------------------------------
        # 2️⃣ 30M CHOCH (HARD EXIT)
        # --------------------------------------------------
        if choch_level_30m is not None:
            if trend == "BULLISH" and c30.close < choch_level_30m:
                return {"status": 2, "time": t30}

            if trend == "BEARISH" and c30.close > choch_level_30m:
                return {"status": 2, "time": t30}

        # --------------------------------------------------
        # 7️⃣ 30M BOS → RESET LEG
        # --------------------------------------------------
        if impulse_high is not None and trend == "BULLISH" and c30.high > impulse_high:
            pullback_confirmed = False
            impulse_high = c30.high
            impulse_low = None
            opp_count = 0
            pois = []
            poi_index = 0
            trade_taken = False
            choch_level_30m = c30.low

        if impulse_low is not None and trend == "BEARISH" and c30.low < impulse_low:
            pullback_confirmed = False
            impulse_low = c30.low
            impulse_high = None
            opp_count = 0
            pois = []
            poi_index = 0
            trade_taken = False
            choch_level_30m = c30.high

        # --------------------------------------------------
        # 3️⃣ WAIT FOR 30M PULLBACK
        # --------------------------------------------------
        if not pullback_confirmed:

            if trend == "BULLISH":
                if impulse_high is None or c30.high > impulse_high:
                    impulse_high = c30.high
                    choch_level_30m = c30.low
                    opp_count = 0
                    continue

                if c30.close < c30.open:
                    opp_count += 1
                else:
                    opp_count = 0

                depth_ok = (
                    (impulse_high - c30.low)
                    / max(impulse_high - htf_swing_low, 1e-9)
                ) >= pullback_pct

                if opp_count >= min_pullback_candles or depth_ok:
                    pullback_confirmed = True
                    pullback_time = t30
                    impulse_low = c30.low

            else:
                if impulse_low is None or c30.low < impulse_low:
                    impulse_low = c30.low
                    choch_level_30m = c30.high
                    opp_count = 0
                    continue

                if c30.close > c30.open:
                    opp_count += 1
                else:
                    opp_count = 0

                depth_ok = (
                    (c30.high - impulse_low)
                    / max(htf_swing_high - impulse_low, 1e-9)
                ) >= pullback_pct

                if opp_count >= min_pullback_candles or depth_ok:
                    pullback_confirmed = True
                    pullback_time = t30
                    impulse_high = c30.high

            continue

        # --------------------------------------------------
        # 4️⃣ POI DETECTION (ONCE PER LEG)
        # --------------------------------------------------
        if pullback_confirmed and not pois:
            swing_df = df_30m.loc[:pullback_time]
            pois = detect_pois_from_swing(swing_df, trend)
            continue

        # --------------------------------------------------
        # 5️⃣ PROCESS CURRENT 30M CANDLE
        # --------------------------------------------------
        if trade_taken:
            continue

        if poi_index >= len(pois):
            continue

        active_poi = pois[poi_index]
        poi_tapped = False

        if trend == "BULLISH":
            if active_poi["type"] == "OB" and c30.low <= active_poi["price_high"]:
                poi_tapped = True
            if active_poi["type"] == "LIQ" and c30.low <= active_poi["price_low"]:
                poi_tapped = True
        else:
            if active_poi["type"] == "OB" and c30.high >= active_poi["price_low"]:
                poi_tapped = True
            if active_poi["type"] == "LIQ" and c30.high >= active_poi["price_high"]:
                poi_tapped = True

        if not poi_tapped:
            continue

        # --------------------------------------------------
        # 6️⃣ REAL-TIME 5M PROCESSING (INSIDE 30M)
        # --------------------------------------------------
        m5_live = df_5m[
            (df_5m.index >= pullback_time) &
            (df_5m.index <= t30)
        ]

        opp_trend = "BEARISH" if trend == "BULLISH" else "BULLISH"

        for t5, c5 in m5_live.iterrows():

            protected_5m = process_structure_and_return_last_swing(
                df=m5_live.loc[:t5],
                trend=opp_trend,
            )

            if protected_5m is None:
                continue

            if trend == "BULLISH" and c5.close > protected_5m:
                trade_details = plan_trade_from_choch_leg(
                    m5_live.loc[:t5],
                    trend
                )
                trade_taken = True
                break

            if trend == "BEARISH" and c5.close < protected_5m:
                trade_details = plan_trade_from_choch_leg(
                    m5_live.loc[:t5],
                    trend
                )
                trade_taken = True
                break

        poi_index += 1

    return {"status": "CONTINUE"}
