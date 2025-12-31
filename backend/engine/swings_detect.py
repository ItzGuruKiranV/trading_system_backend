import pandas as pd
import sys
import os
import matplotlib.pyplot as plt
from typing import Optional, Dict, List
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'debug'))
from debug.swings_plot import swing_state  
from engine.poi_detection import detect_pois_from_swing
from engine.mins_choch import process_structure_and_return_last_swing
from engine.plan_trade_5mins import plan_trade_from_choch_leg

# 🔐 GLOBAL EVENT INDEX GUARD  (STRICTLY INCREASING)
EVENT_LOG: list[swing_state] = []
last_logged_index = -1

# 🔐 CENTRALIZED EVENT LOGGER
def log_event(
    idx,
    t,
    trend,
    event,
    validation_tf,
    swing_high=None,
    swing_low=None,
    active_poi=None,
    trade_details=None,
    rr_ratio=None,
    **extra
):
    TF_OFFSET = {"4h": 1_000_000, "5m": 0}

    # last index per timeframe
    last_idx = next(
        (e.index for e in reversed(EVENT_LOG)
         if e.extra.get("validation_tf") == validation_tf),
        -1
    )

    if idx <= last_idx:
        return

    effective_idx = TF_OFFSET.get(validation_tf, 0) + idx

    for e in EVENT_LOG:
        prev_tf = e.extra.get("validation_tf")
        if prev_tf not in TF_OFFSET:
            continue

        prev_effective_idx = TF_OFFSET[prev_tf] + e.index
        if prev_effective_idx == effective_idx and e.event == event:
            return

    state=swing_state(
        index=idx,
        time=t,
        trend=trend,
        event=event,
        validation_tf=validation_tf,
        swing_high=swing_high,
        swing_low=swing_low,
        active_poi=active_poi,
        trade_details=trade_details,
        rr_ratio=rr_ratio,
        liquidity_grabbed=False,
        extra=extra,
    )
    EVENT_LOG.append(state)


def market_structure_mapping(
    df_4h: pd.DataFrame,
    df_5m: pd.DataFrame,
    trend: str,
    bos_time,
    pullback_pct: float = 0.35,
    min_pullback_candles: int = 5,
    depth: int = 0,
    max_depth: int = 50,
) -> List[swing_state]:

    
    if depth == 0:
        EVENT_LOG.clear()
        global last_logged_index
        last_logged_index = -1


    indent = "    " * depth
    trend = trend.upper()
    print(f"\n{indent}🚀 MARKET STRUCTURE START")
        
    # 🔥 INITIAL STATE — LOG SAFELY AT INDEX 0
    log_event(idx=0, t=bos_time, trend=trend, event="start", validation_tf="4h")

    if depth >= max_depth:
        print(f"{indent}⛔ Max recursion depth reached")
        return EVENT_LOG

    if len(df_4h) < 5:
        print(f"{indent}❌ Not enough 4H data after BOS")
        return EVENT_LOG
    first_candle = df_4h.iloc[0]

    if trend == "BULLISH":
        protected_low = first_candle.low
        protected_high = None
    else:
        protected_high = first_candle.high
        protected_low = None

    print("Protected swing locked")

    # PULLBACK VALIDATION (STARTS FROM BOS ONLY)
    candidate_high = None
    candidate_low = None

    bearish_count = 0
    bullish_count = 0

    pullback_confirmed = False
    pullback_time = None

    pullback_df = df_4h.loc[df_4h.index >= bos_time]

    for t, c in pullback_df.iterrows():

        if trend == "BULLISH":
            if candidate_high is None or c.high > candidate_high:
                candidate_high = c.high
                bearish_count = 0
                continue

            if c.close < c.open and c.high < candidate_high:
                bearish_count += 1
            else:
                bearish_count = 0

            # 3️⃣ Depth validation
            depth_valid = (
                (candidate_high - c.low)
                / max(candidate_high - protected_low, 1e-9)
            ) >= pullback_pct

            # 4️⃣ Pullback confirmed
            if bearish_count >= min_pullback_candles or depth_valid:
                pullback_confirmed = True
                pullback_time = t
                swing_high = candidate_high
                swing_low = protected_low

                print("✅ Pullback confirmed (BULLISH)")
                print(f"Swing High : {swing_high}")
                print(f"Swing Low  : {swing_low}")
                print(f"Time       : {pullback_time}")
                # 🔥 PULLBACK CONFIRMED — LOG HERE
                log_event(
                    idx=df_4h.index.get_loc(pullback_time),
                    t=pullback_time,
                    trend=trend,
                    event="pullback_confirmed",
                    swing_high=swing_high,
                    swing_low=swing_low,
                    validation_tf="4h"
                )           
                break
        else:

            if candidate_low is None or c.low < candidate_low:
                candidate_low = c.low
                bullish_count = 0
                continue

            if c.close > c.open and c.low > candidate_low:
                bullish_count += 1
            else:
                bullish_count = 0

            depth_valid = (
                (c.high - candidate_low)
                / max(protected_high - candidate_low, 1e-9)
            ) >= pullback_pct

            if bullish_count >= min_pullback_candles or depth_valid:
                pullback_confirmed = True
                pullback_time = t
                swing_low = candidate_low
                swing_high = protected_high

                print("✅ Pullback confirmed (BEARISH)")
                print(f"Swing Low  : {swing_low}")
                print(f"Swing High : {swing_high}")
                print(f"Time       : {pullback_time}")
                # 🔥 PULLBACK CONFIRMED — LOG HERE
                log_event(
                    idx=df_4h.index.get_loc(pullback_time),
                    t=pullback_time,
                    trend=trend,
                    event="pullback_confirmed",
                    swing_high=swing_high,
                    swing_low=swing_low,
                    validation_tf="4h"
                )
                break  

    if not pullback_confirmed:
        print("❌ No valid pullback")
        return EVENT_LOG

    # ==================================================
    # PHASE 3 — POI DETECTION (FULL LEG)
    # ==================================================
    swing_df = df_4h.loc[df_4h.index[0]:pullback_time]

    pois = detect_pois_from_swing(
        ohlc_df=swing_df,
        trend=trend,
    )

    print(f"{indent}🎯 POIs detected: {len(pois)}")

    # 🔥 POI DETECTED — LOG ALL
    if pois:
        for poi in pois:
            poi_idx = df_4h.index.get_loc(poi["time"])
            poi_type = poi["type"]
            trend = poi["trend"]
            low = poi["price_low"]
            high = poi["price_high"]

            log_event(
                idx=poi_idx,
                t=poi["time"],
                trend=trend,
                event="poi_detected",   
                poi_type=poi_type,
                price_low=low,
                price_high=high,
                active_poi=poi,      # Full POI dict, useful for plotting
                validation_tf="4h"
            )

    # ==================================================
    # PHASE 4 — POST-PULLBACK MONITORING (5M DRIVEN)
    # ==================================================

    df_4h_post = df_4h.loc[df_4h.index > pullback_time]
    df_5m_post = df_5m.loc[df_5m.index > pullback_time]

    if df_5m_post.empty:
        print(f"{indent}❌ No 5M data after pullback")
        return EVENT_LOG

    poi_active = False
    trade_details = None
    trade_active = False
    active_poi = None
    poi_tapped = False
    protected_5m_point = None
    opp_pullback_count = 0
    choch_validated = False
    entry_filled = False

    print(f"{indent}▶ Monitoring 5M candles after pullback...")

    for t5, c5 in df_5m_post.iterrows():

        if trade_active and trade_details:

            if not entry_filled:

                # Check entry fill FIRST (before TP/SL)
                entry_filled_this_candle = False
                
                if trend == "BULLISH":
                    if c5.low <= trade_details["entry"] <= c5.high:
                        entry_filled_this_candle = True
                else:
                    if c5.low <= trade_details["entry"] <= c5.high:
                        entry_filled_this_candle = True

                if entry_filled_this_candle:
                    entry_filled = True
                    trade_details["status"] = "OPEN"
                    trade_details["entry_time"] = t5
                    print(f"{indent}🟢 ENTRY FILLED @ {trade_details['entry']} @ {t5}")
                    # 🔥 ENTRY FILLED — LOG HERE
                    log_event(
                        idx=df_5m.index.get_loc(t5),
                        t=t5,
                        trend=trend,
                        event="entry_filled",
                        trade_details=trade_details,
                        validation_tf="5m"
                    )

                    # Continue to check TP/SL in same iteration
                else:
                    # Entry not filled - check if TP hit without entry
                    if trend == "BULLISH":
                        if c5.high >= trade_details["tp"]:
                            print(f"{indent}🟩 TP HIT WITHOUT ENTRY → TRADE INVALID")
                            # 🔥 TP WITHOUT ENTRY — LOG HERE
                            log_event(
                                idx=df_5m.index.get_loc(t5),
                                t=t5,
                                trend=trend,
                                event="tp_no_entry",
                                trade_details=trade_details,
                                validation_tf="5m"
                            )

                            # 🔥 RESET EVERYTHING
                            trade_active = False
                            trade_details = None
                            entry_filled = False
                            poi_active = False
                            protected_5m_point = None
                            opp_pullback_count = 0
                            choch_validated = False
                            continue
                    else:
                        if c5.low <= trade_details["tp"]:
                            print(f"{indent}🟩 TP HIT WITHOUT ENTRY → TRADE INVALID")
                            # 🔥 TP WITHOUT ENTRY — LOG HERE
                            log_event(
                                idx=df_5m.index.get_loc(t5),
                                t=t5,
                                trend=trend,
                                event="tp_no_entry",
                                trade_details=trade_details,
                                validation_tf="5m"
                            )

                            # 🔥 RESET EVERYTHING
                            trade_active = False
                            trade_details = None
                            entry_filled = False
                            poi_active = False
                            protected_5m_point = None
                            opp_pullback_count = 0
                            choch_validated = False
                            continue
                    continue

            if entry_filled:

                if trend == "BULLISH":

                    if c5.low <= trade_details["sl"]:
                        print(f"{indent}🟥 SL HIT")
                        # 🔥 SL HIT — LOG HERE
                        log_event(
                                idx=df_5m.index.get_loc(t5),
                                t=t5,
                                trend=trend,
                                event="sl_hit",
                                trade_details=trade_details,
                                validation_tf="5m"
                            )

                        trade_active = False
                        trade_details = None
                        entry_filled = False
                        poi_active = False
                        protected_5m_point = None
                        opp_pullback_count = 0
                        choch_validated = False
                        continue

                    # TAKE PROFIT
                    elif c5.high >= trade_details["tp"]:
                        print(f"{indent}🟩 TP HIT")
                        # 🔥 TP HIT — LOG HERE
                        log_event(
                            idx=df_5m.index.get_loc(t5),
                            t=t5,
                            trend=trend,
                            event="tp_hit",
                            trade_details=trade_details,
                            validation_tf="5m"
                        )


                        trade_active = False
                        trade_details = None
                        entry_filled = False
                        poi_active = False
                        protected_5m_point = None
                        opp_pullback_count = 0
                        choch_validated = False
                        continue

                else:  

                    if c5.high >= trade_details["sl"]:
                        print(f"{indent}🟥 SL HIT")
                        # 🔥 SL HIT — LOG HERE
                        log_event(
                            idx=df_5m.index.get_loc(t5),
                            t=t5,
                            trend=trend,
                            event="sl_hit",
                            trade_details=trade_details,
                            validation_tf="5m"
                        )

                        trade_active = False
                        trade_details = None
                        entry_filled = False
                        poi_active = False
                        protected_5m_point = None
                        opp_pullback_count = 0
                        choch_validated = False
                        continue

                    # TAKE PROFIT
                    elif c5.low <= trade_details["tp"]:
                        print(f"{indent}🟩 TP HIT")
                        # 🔥 TP HIT — LOG HERE
                        log_event(
                            idx=df_5m.index.get_loc(t5),
                            t=t5,
                            trend=trend,
                            event="tp_hit",
                            trade_details=trade_details,
                            validation_tf="5m"
                        )

                        trade_active = False
                        trade_details = None
                        entry_filled = False
                        poi_active = False
                        protected_5m_point = None
                        opp_pullback_count = 0
                        choch_validated = False
                        continue

                continue
        # --------------------------------------------------
        # 1️⃣ STRUCTURE INVALIDATION (CHOCH) — ONLY AFTER POI
        # --------------------------------------------------
        if not trade_active:

            if trend == "BULLISH" and c5.close < swing_low:
                print(f"{indent}🟥 CHOCH @ {t5} in 4h")

                # 🔥 CHOCH — LOG HERE
                log_event(
                    idx=df_5m.index.get_loc(t5),
                    t=t5,
                    trend=trend,
                    event="choch",
                    swing_low=swing_low if trend == "BULLISH" else None,
                    swing_high=swing_high if trend == "BEARISH" else None,
                    active_poi=active_poi,        # optional but very useful
                    trade_details=None ,           # important: no trade yet
                    validation_tf="5m"
                )

                # trim before swing_high
                df_4h_new = df_4h.loc[df_4h.index >= pullback_time]
                df_5m_new = df_5m.loc[df_5m.index >= pullback_time]

                return market_structure_mapping(
                    df_4h=df_4h_new,
                    df_5m=df_5m_new,
                    trend="BEARISH",
                    bos_time=t5,
                    depth=depth + 1,
                )

            if trend == "BEARISH" and c5.close > swing_high:
                print(f"{indent}🟥 CHOCH @ {t5} in 4h")

                # 🔥 CHOCH — LOG HERE
                log_event(
                    idx=df_5m.index.get_loc(t5),
                    t=t5,
                    trend=trend,
                    event="choch",
                    validation_tf="5m"
                )

                df_4h_new = df_4h.loc[df_4h.index >= pullback_time]
                df_5m_new = df_5m.loc[df_5m.index >= pullback_time]
                
                return market_structure_mapping(
                    df_4h=df_4h_new,
                    df_5m=df_5m_new,
                    trend="BULLISH",
                    bos_time=t5,
                    depth=depth + 1,
                )

        # --------------------------------------------------
        # 2️⃣ BOS WITHOUT POI (CONTINUATION)
        # --------------------------------------------------
        if not poi_active:

            if trend == "BULLISH" and c5.close > swing_high:
                print(f"{indent}🟦 BOS WITHOUT POI @ {t5} in 4h")

                log_event(
                    idx=df_5m.index.get_loc(t5),
                    t=t5,
                    trend=trend,
                    event="bos_without_poi",
                    swing_high=swing_high,
                    swing_low=swing_low,
                    active_poi=None,
                    trade_details=None,
                    validation_tf="5m"
                )

                # lowest low from swing_high → BOS
                range_low = df_5m.loc[pullback_time:t5]["low"].min()

                df_4h_new = df_4h.loc[df_4h.index >= t5]
                df_5m_new = df_5m.loc[df_5m.index >= t5]

                
                return market_structure_mapping(
                    df_4h=df_4h_new,
                    df_5m=df_5m_new,
                    trend="BULLISH",
                    bos_time=t5,
                    depth=depth + 1,
                )

            if trend == "BEARISH" and c5.close < swing_low:
                print(f"{indent}🟦 BOS WITHOUT POI @ {t5} in 4h")

                # 🔥 BOS — LOG HERE
                log_event(
                    idx=df_5m.index.get_loc(t5),
                    t=t5,
                    trend=trend,
                    event="bos_without_poi",
                    swing_low=swing_low if trend == "BEARISH" else None,
                    swing_high=swing_high if trend == "BULLISH" else None,
                    validation_tf="5m"
                )

                range_high = df_5m.loc[pullback_time:t5]["high"].max()

                df_4h_new = df_4h.loc[df_4h["high"] <= range_high]
                df_5m_new = df_5m.loc[df_5m["high"] <= range_high]
                
                return market_structure_mapping( 
                    df_4h=df_4h_new,
                    df_5m=df_5m_new,
                    trend="BEARISH",
                    bos_time=t5,
                    depth=depth + 1,
                )
        # --------------------------------------------------
        # POI INVALIDATION (TYPE + ORDER AWARE)
        # --------------------------------------------------
        if poi_active:

            active_poi = pois[0]
            next_poi = pois[1] if len(pois) > 1 else None

            p0_type = active_poi["type"]
            p0_low  = active_poi["price_low"]
            p0_high = active_poi["price_high"]

            invalidation_level = None

            # =========================
            # BULLISH TREND
            # =========================
            if trend == "BULLISH":

                if next_poi:
                    p1_type = next_poi["type"]
                    p1_low  = next_poi["price_low"]
                    p1_high = next_poi["price_high"]

                    if p0_type == "OB" and p1_type == "OB":
                        invalidation_level = (p0_high + p1_high) / 2

                    elif p0_type == "OB" and p1_type == "LIQ":
                        invalidation_level = (p0_high + p1_low) / 2

                    elif p0_type == "LIQ" and p1_type == "LIQ":
                        invalidation_level = (p0_low + p1_low) / 2

                    else:
                        invalidation_level = None  # invalid structure

                else:
                    # No next POI → use swing low
                    if p0_type == "OB":
                        invalidation_level = (p0_high + swing_low) / 2
                    else:  # LIQ
                        invalidation_level = (p0_low + swing_low) / 2

                if invalidation_level is not None and c5.low < invalidation_level:
                    print(f"{indent}❌ POI INVALIDATED @ {t5}")
                    print(f"{indent}   Level broken: {invalidation_level}")
                    # 🔥 POI INVALIDATED — LOG HERE
                    log_event(
                        idx=df_5m.index.get_loc(t5),
                        t=t5,
                        trend=trend,
                        event="poi_invalidated",
                        active_poi=active_poi,
                        validation_tf="5m"
                    )
                    if pois:
                        pois.pop(0)
                        poi_active = False
                        active_poi = None
                        protected_5m_point = None
                        continue

            # =========================
            # BEARISH TREND
            # =========================
            else:

                if next_poi:
                    p1_type = next_poi["type"]
                    p1_low  = next_poi["price_low"]
                    p1_high = next_poi["price_high"]

                    if p0_type == "OB" and p1_type == "OB":
                        invalidation_level = (p0_low + p1_low) / 2

                    elif p0_type == "OB" and p1_type == "LIQ":
                        invalidation_level = (p0_low + p1_high) / 2

                    elif p0_type == "LIQ" and p1_type == "LIQ":
                        invalidation_level = (p0_high + p1_high) / 2

                    else:
                        invalidation_level = None

                else:
                    if p0_type == "OB":
                        invalidation_level = (p0_low + swing_high) / 2
                    else:  # LIQ
                        invalidation_level = (p0_high + swing_high) / 2

                if invalidation_level is not None and c5.high > invalidation_level:
                    print(f"{indent}❌ POI INVALIDATED @ {t5}")
                    print(f"{indent}   Level broken: {invalidation_level}")

                    # 🔥 POI INVALIDATED — LOG HERE
                    log_event(
                        idx=df_5m.index.get_loc(t5),
                        t=t5,
                        trend=trend,
                        event="poi_invalidated",
                        active_poi=active_poi,
                        validation_tf="5m"
                    )

                    if pois:
                        pois.pop(0)
                        poi_active = False
                        active_poi = None
                        protected_5m_point = None
                        continue

        # --------------------------------------------------
        # 3️⃣ POI TAP (TREND + TYPE BASED)
        # --------------------------------------------------
        if not poi_active and pois:

            active_poi = pois[0]   # first POI only
            poi_type = active_poi["type"]

            poi_low = active_poi["price_low"]
            poi_high = active_poi["price_high"]

            if trend == "BULLISH":

                if poi_type == "OB":
                    # OB tapped if candle overlaps with OB range
                    if c5.low <= poi_high and c5.high >= poi_low:
                        poi_tapped = True

                elif poi_type == "LIQ":
                    # LIQ tapped if candle touches or breaks below LIQ low
                    if c5.low <= poi_low:
                        poi_tapped = True

            else:

                if poi_type == "OB":
                    # OB tapped if candle overlaps with OB range
                    if c5.high >= poi_low and c5.low <= poi_high:
                        poi_tapped = True

                elif poi_type == "LIQ":
                    # LIQ tapped if candle touches or breaks above LIQ high
                    if c5.high >= poi_high:
                        poi_tapped = True

            if poi_tapped:
                poi_active = True

                # ⭐ STORE POI ACTIVATION FOR PLOTTING
                active_poi["activation_time"] = t5
                active_poi["activation_idx"] = df_5m.index.get_loc(t5)

                print(f"{indent}🔥 POI TAPPED ({poi_type}) @ {t5}")

                # 🔥 POI TAPPED — LOG HERE
                log_event(
                    idx=df_5m.index.get_loc(t5),
                    t=t5,
                    trend=trend,
                    event="poi_tapped",
                    active_poi=active_poi,
                    swing_high=swing_high,
                    swing_low=swing_low,
                    validation_tf="5m"
                )

                # 🔹 CALL 5M STRUCTURE FUNCTION HERE
                opp_trend = "BEARISH" if trend == "BULLISH" else "BULLISH"

                m5_slice = df_5m.loc[pullback_time:t5]

                protected_5m_point = process_structure_and_return_last_swing(
                    df=m5_slice,
                    trend=opp_trend,
                )
                poi_tapped = False
                # Check if return value is valid (not None and not 0.0 or negative)
                if protected_5m_point is None or protected_5m_point <= 0:
                    print(f"{indent}❌ Invalid 5M structure point: {protected_5m_point}")
                    poi_active = False
                    protected_5m_point = None
                    continue
                print(f"{indent}✅ 5M Protected Point: {protected_5m_point}")
                # 🔥 5M STRUCTURE READY — LOG HERE
                log_event(
                    idx=df_5m.index.get_loc(t5),
                    t=t5,
                    trend=trend,
                    event="m5_structure_ready",
                    swing_high=protected_5m_point if opp_trend == "BEARISH" else None,
                    swing_low=protected_5m_point if opp_trend == "BULLISH" else None,
                    validation_tf="5m"
                )
            else:
                continue

        # --------------------------------------------------
        # 5️⃣ 5M STRUCTURE CHECK (CHOCH / BOS LOGIC)
        # --------------------------------------------------
        if protected_5m_point is not None:
            if trend == "BULLISH":
                # opp_trend is BEARISH, so protected_5m_point is a SWING HIGH
                # CHOCH = break BELOW swing high
                if c5.close < protected_5m_point:
                    broken_level = protected_5m_point
                    choch_validated = True
                    poi_active = False
                    poi_tapped = False
                    if pois:
                        pois.pop(0)
                    protected_5m_point = None

                    # 🔥 5M CHOCH — LOG HERE
                    log_event(
                        idx=df_5m.index.get_loc(t5),
                        t=t5,
                        trend=trend,
                        event="m5_choch",
                        validation_tf="5m",
                        # 🔑 STRUCTURE DETAILS (for plotting)
                        broken_level=broken_level,   # exact level broken
                        structure_type="HL" if opp_trend == "BULLISH" else "LH",
                        
                        # 🔑 CONTEXT (optional but very useful)
                        active_poi=active_poi
                    )

                elif c5.close < c5.open:
                    opp_pullback_count += 1
                elif c5.low < protected_5m_point and opp_pullback_count < 2:
                    opp_pullback_count = 0

                # 🔹 BOS after valid pullback (new higher high)
                if opp_pullback_count >= 2 and c5.high > protected_5m_point:
                    old_level = protected_5m_point
                    new_level = c5.high
                    protected_5m_point = new_level
                    opp_pullback_count = 0

                    # 🔥 5M BOS — LOG HERE
                    log_event(
                        idx=df_5m.index.get_loc(t5),
                        t=t5,
                        trend=trend,
                        event="m5_bos",
                        validation_tf="5m",
                        broken_level=old_level,
                        new_structure_level=new_level,
                        structure_type="HH",
                        active_poi=active_poi,
                    )

            else:
                # opp_trend is BULLISH, so protected_5m_point is a SWING LOW
                # CHOCH = break ABOVE swing low
                if c5.close > protected_5m_point:
                    broken_level = protected_5m_point
                    choch_validated = True
                    poi_active = False
                    poi_tapped = False
                    if pois:
                        pois.pop(0)
                    protected_5m_point = None

                    # 🔥 5M CHOCH — LOG HERE
                    log_event(
                        idx=df_5m.index.get_loc(t5),
                        t=t5,
                        trend=trend,
                        event="m5_choch",
                        validation_tf="5m",

                        # 🔑 STRUCTURE DETAILS (for plotting)
                        protected_5m_point=broken_level,   # exact level broken
                        structure_type = "LH" if trend == "BULLISH" else "HL",

                        # 🔑 CONTEXT (optional but very useful)
                        active_poi=active_poi
                    )


                elif c5.close > c5.open:
                    opp_pullback_count += 1
                elif c5.high > protected_5m_point and opp_pullback_count < 2:
                    opp_pullback_count = 0

                # 🔹 BOS after valid pullback (new lower low)
                if opp_pullback_count >= 2 and c5.low < protected_5m_point:
                    old_level = protected_5m_point      # 🔑 store broken level
                    new_level = c5.low                  # 🔑 new LL

                    protected_5m_point = new_level
                    opp_pullback_count = 0

                    # 🔥 5M BOS — LOG HERE
                    log_event(
                        idx=df_5m.index.get_loc(t5),
                        t=t5,
                        trend=trend,
                        event="m5_bos",
                        validation_tf="5m",

                        # 🔑 STRUCTURE DETAILS (for plotting)
                        protected_5m_point=old_level,    # level that got broken
                        new_structure_level=new_level,   # new LL
                        structure_type="LL",             # Lower Low

                        # 🔑 CONTEXT
                        active_poi=active_poi
                    )
        # --------------------------------------------------
        # 6️⃣ 5M CHOCH → TRADE (EXECUTE ONCE, THEN MANAGE)
        # --------------------------------------------------
        if choch_validated and not trade_active:

            print(f"{indent}🎯 5M CHOCH CONFIRMED → EXECUTING TRADE")

            # CHOCH leg = from pullback_time to choch candle (t5)
            # Find first 5M candle after pullback_time
            first_5m_after_pullback = df_5m.loc[df_5m.index > pullback_time]
            if first_5m_after_pullback.empty:
                print(f"{indent}❌ No 5M data after pullback for CHOCH leg")
                choch_validated = False
                continue
            
            choch_leg_start = first_5m_after_pullback.index[0]
            choch_leg_df = df_5m.loc[choch_leg_start:t5]
            
            if len(choch_leg_df) < 2:
                print(f"{indent}❌ CHOCH leg too short: {len(choch_leg_df)} candles")
                choch_validated = False
                continue

            trade = plan_trade_from_choch_leg(
                choch_leg_df=choch_leg_df,
                trend=trend,
            )
            choch_validated = False
            print(trade)

            if trade:

                # -------------------------------
                # TP VALIDATION AGAINST HTF SWING
                # -------------------------------
                if trend == "BULLISH" and trade["tp"] >= swing_high:
                    print(f"{indent}❌ TP ABOVE SWING HIGH → TRADE REJECTED")
                    # 🔥 TRADE REJECTED — LOG HERE
                    log_event(
                        idx=df_5m.index.get_loc(t5),
                        t=t5,
                        trend=trend,
                        event="trade_rejected",
                        rejection_reason="tp_above_htf_swing_high",
                        tp=trade["tp"],
                        htf_swing=swing_high,
                        active_poi=active_poi,
                        validation_tf="5m"
                    )

                    choch_validated = False
                    continue

                if trend == "BEARISH" and trade["tp"] <= swing_low:
                    print(f"{indent}❌ TP BELOW SWING LOW → TRADE REJECTED")
                    # 🔥 TRADE REJECTED — LOG HERE
                    log_event(
                        idx=df_5m.index.get_loc(t5),
                        t=t5,
                        trend=trend,
                        event="trade_rejected",
                        # 🔑 REJECTION DETAILS
                        rejection_reason="tp_below_htf_swing_low",
                        tp=trade["tp"],
                        htf_swing=swing_low,
                        # 🔑 CONTEXT (for plotting / debugging)
                        active_poi=active_poi,
                        validation_tf="5m"
                    )


                    choch_validated = False
                    continue

                # -------------------------------
                # STORE TRADE (DO NOT RETURN)
                # -------------------------------
                trade_details = {
                    "entry": trade["entry"],
                    "sl": trade["sl"],
                    "tp": trade["tp"],
                    "direction": trend,
                    "choch_time": t5,
                    "status": "PENDING",
                }

                trade_active = True
                print(f"{indent}✅ TRADE STORED → WAITING FOR SL / TP")
                # 🔥 TRADE ENTRY → 1:3 R:R LINES!
                rr_ratio = abs((trade_details["tp"] - trade_details["entry"]) / (trade_details["entry"] - trade_details["sl"]))
                # 🔥 TRADE ENTRY — LOG HERE
                log_event(
                    idx=df_5m.index.get_loc(t5),
                    t=t5,
                    trend=trend,
                    event="trade_entry",
                    validation_tf="5m",

                    # 🔑 TRADE DETAILS
                    trade_details=trade_details,
                    rr_ratio=rr_ratio,

                    # 🔑 CONTEXT
                    active_poi=active_poi,
                )

            else:
                print(f"{indent}❌ Trade logic rejected")
                choch_validated = False

    return EVENT_LOG
