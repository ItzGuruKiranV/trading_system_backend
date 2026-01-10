import pandas as pd
import sys
import os
import matplotlib.pyplot as plt
from typing import Optional, Dict, List
from dataclasses import dataclass
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'debug'))
from debug.swings_plot import swing_state  
from engine.poi_detection import detect_pois_from_swing
from engine.mins_choch import process_structure_and_return_last_swing
from engine.plan_trade_5mins import plan_trade_from_choch_leg
all_legs_event_logs: List[List[Dict]] = []
leg_5m_events: List[Dict] = []


MASTER_LOG = []

def log_event_master(
    idx,
    time,
    trend,
    event,           # pullback, swing, bos, choch, poi
    reason=None,     # why the event happened
    candle=None,     # candle data if relevant
    swing_high=None,
    swing_low=None,
    candle_count=None,
    poi_type=None,   # OB or LIQ
    poi_high=None,
    poi_low=None,
    activation_time=None,
    candidate_low=None,     
    candidate_high=None,     
    protected_low=None,      
    protected_high=None,     
    bullish_count=None,      
    bearish_count=None,      
    depth_ratio=None,        
    depth_valid=None         
):
    # ⚡ Minimal change: fallback to numeric if None
    protected_low = protected_low if protected_low is not None else None
    protected_high = protected_high if protected_high is not None else None

    MASTER_LOG.append({
        "index": idx,
        "time": time,
        "trend": trend,
        "event": event,
        "reason": reason,
        "candle_count": candle_count,
        "open": getattr(candle, "open", None),
        "high": getattr(candle, "high", None),
        "low": getattr(candle, "low", None),
        "close": getattr(candle, "close", None),
        "swing_high": swing_high,
        "swing_low": swing_low,
        "poi_type": poi_type,
        "poi_high": poi_high,
        "poi_low": poi_low,
        "poi_activation_time": activation_time,
        "candidate_low": candidate_low,       
        "candidate_high": candidate_high,
        "protected_low": protected_low,
        "protected_high": protected_high,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "depth_ratio": depth_ratio,
        "depth_valid": depth_valid       
    })



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
    pullback_pct: float = 0.90,
    min_pullback_candles: int = 10,
    depth: int = 0,
    max_depth: int = 50,
) -> List[swing_state]:

    tapped_pois = []
    protected_5m_points = []
    leg_5m_structure = []
    all_5m_obs: list = []          # stores all OBs detected
    all_5m_trades: list = []

    if depth == 0:
        EVENT_LOG.clear()
        MASTER_LOG.clear()
        global last_logged_index
        last_logged_index = -1


    indent = "    " * depth
    trend = trend.upper()
    print(f"\n{indent}🚀 MARKET STRUCTURE START")
        
    # 🔥 INITIAL STATE — LOG SAFELY AT INDEX 0
    log_event(idx=0, t=bos_time, trend=trend, event="start", validation_tf="4h")
    log_event_master(idx=0, time=bos_time, trend=trend, event="start")


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
    swinh_high_time=None
    swing_low_time=None
    protected_5m_point = None
    protected_5m_time = None

    swing_low_5m = None
    swing_low_range_start = None

    swing_high_5m = None
    swing_high_range_start = None

    opp_pullback_count = 0

    pullback_df = df_4h.loc[df_4h.index >= bos_time]

    start_idx = df_4h.index.get_loc(pullback_df.index[0]) if not df_4h.empty else 0

    for offset_idx, (t, c) in enumerate(pullback_df.iterrows()):
        idx = start_idx + offset_idx  # correct 4H index for logging

        if trend == "BULLISH":
            if candidate_high is None or c.high > candidate_high:
                candidate_high = c.high
                bearish_count = 0
                if protected_low is None or candidate_high is None:
                    continue

                depth_ratio = (
                    (candidate_high - min(c.low, c.close))
                    / max(candidate_high - protected_low, 1e-9)
                )

                depth_valid = depth_ratio >= pullback_pct

                log_event_master(
                    time=t,
                    idx=df_4h.index.get_loc(t),
                    candle=c,
                    trend=trend,
                    candidate_high=candidate_high,
                    protected_low=protected_low,
                    bearish_count=bearish_count,
                    depth_ratio=depth_ratio,
                    depth_valid=depth_valid,
                    event="pullback_check_bullish"  
                )

                continue

            if c.close < c.open and c.high < candidate_high:
                bearish_count += 1

            # 3️⃣ Depth validation
            if protected_low is None or candidate_high is None:
                continue

            depth_ratio = (
                    (candidate_high - min(c.low, c.close))
                    / max(candidate_high - protected_low, 1e-9)
                )

            depth_valid = depth_ratio >= pullback_pct
            # 🔍 Log every candle
            log_event_master(
                time=t,
                idx=df_4h.index.get_loc(t),
                candle=c,
                trend=trend,
                candidate_high=candidate_high,
                protected_low=protected_low,
                bearish_count=bearish_count,
                depth_ratio=depth_ratio,
                depth_valid=depth_valid,
                event="pullback_check_bullish"
            )

            # 4️⃣ Pullback confirmed
            if bearish_count >= min_pullback_candles or depth_valid:
                pullback_confirmed = True
                pullback_time = t
                swing_high = candidate_high
                swing_low = protected_low

                # Determine reason based on depth or candle count
                if bearish_count >= min_pullback_candles:
                    reason = f"confirmed_by_candle_count ({bearish_count})"
                elif depth_valid:
                    reason = f"confirmed_by_depth (depth_ratio={depth_ratio:.3f})"
                else:
                    reason = "not_valid"

                print("✅ Pullback confirmed (BULLISH)")
                print(f"Swing High : {swing_high}")
                print(f"Swing Low  : {swing_low}")
                print(f"Time       : {pullback_time}")
                # 🔥 PULLBACK CONFIRMED — LOG HERE

                log_event_master(
                    idx=df_4h.index.get_loc(t),
                    time=pullback_time,
                    trend=trend,
                    event="pullback_confirmed",
                    reason=reason,
                    candle=c,
                    swing_high=swing_high,
                    swing_low=swing_low,
                    candle_count=bearish_count
                )
                log_event(
                    idx=df_4h.index.get_loc(t),
                    t=pullback_time,
                    trend=trend,
                    event="pullback_confirmed",
                    validation_tf="4h",
                    swing_high=swing_high,
                    swing_low=swing_low,
                )        
                    
                break
        else:

            if candidate_low is None or c.low < candidate_low:
                candidate_low = c.low
                bullish_count = 0
                if protected_high is None or candidate_low is None:
                    continue

                depth_ratio = (
                    (c.high - candidate_low)
                    / max(protected_high - candidate_low, 1e-9)
                )
                depth_valid = depth_ratio >= pullback_pct
                log_event_master(
                    time=t,
                    idx=df_4h.index.get_loc(t),
                    candle=c,
                    trend=trend,
                    candidate_low=candidate_low,
                    protected_high=protected_high,
                    bullish_count=bullish_count,
                    depth_ratio=depth_ratio,
                    depth_valid=depth_valid,
                    event="pullback_check_bearish"
                )

                continue

            if c.close > c.open and c.low > candidate_low:
                bullish_count += 1

            # 3️⃣ Depth validation
            if protected_high is None or candidate_low is None:
                continue

            depth_ratio = (
                (c.high - candidate_low)
                / max(protected_high - candidate_low, 1e-9)
            )
            depth_valid = depth_ratio >= pullback_pct
            # 🔍 Log every candle
            log_event_master(
                time=t,
                idx=df_4h.index.get_loc(t),
                candle=c,
                trend=trend,
                candidate_low=candidate_low,
                protected_high=protected_high,
                bullish_count=bullish_count,
                depth_ratio=depth_ratio,
                depth_valid=depth_valid,
                event="pullback_check_bearish"
            )

            if bullish_count >= min_pullback_candles or depth_valid:
                pullback_confirmed = True
                pullback_time = t
                swing_low = candidate_low
                swing_high = protected_high
                
                if bullish_count >= min_pullback_candles:
                    reason = f"confirmed_by_candle_count ({bullish_count})"
                elif depth_valid:
                    reason = f"confirmed_by_depth (depth_ratio={depth_ratio:.3f})"
                else:
                    reason = "not_valid"
                print("✅ Pullback confirmed (BEARISH)")
                print(f"Swing Low  : {swing_low}")
                print(f"Swing High : {swing_high}")
                print(f"Time       : {pullback_time}")
                
                # 🔥 PULLBACK CONFIRMED — LOG HERE
                log_event_master(
                    idx=df_4h.index.get_loc(t),
                    time=pullback_time,
                    trend=trend,
                    event="pullback_confirmed",
                    reason=reason,
                    candle=c,
                    swing_high=swing_high,
                    swing_low=swing_low,
                    candle_count=bullish_count
                )

                log_event(
                    idx=df_4h.index.get_loc(t),
                    t=t,
                    trend=trend,
                    event="pullback_confirmed",
                    validation_tf="4h",
                    swing_high=swing_high,
                    swing_low=swing_low,
                )
                break  
        
    # ==================================================
    # PHASE 3 — POI DETECTION (FULL LEG)
    # ==================================================
    swing_df = df_4h.loc[df_4h.index[0]:pullback_time]
    leg_start_4h = df_4h.index[0]  # start of swing_df
    leg_end_4h = pullback_time      # end of swing_df

    # Align 4H swing to nearest 5M candles
    idx_start = df_5m.index.get_indexer([leg_start_4h], method="ffill")[0]
    leg_start_5m = df_5m.index[idx_start]
    idx_end = df_5m.index.get_indexer([leg_end_4h], method="ffill")[0]
    leg_end_5m = df_5m.index[idx_end]

    # Detect POIs
    pois = detect_pois_from_swing(
        ohlc_df=swing_df,
        trend=trend,
    )
    for p in pois:
        p["state"] = "ACTIVE"

    print(f"{indent}🎯 POIs detected: {len(pois)}")

    # Deduplicate POIs
    seen = set()
    unique_pois = []
    for poi in pois:
        key = (poi["time"], poi["price_low"], poi["price_high"], poi["type"])
        if key not in seen:
            seen.add(key)
            unique_pois.append(poi)

    mapped_pois = []

    # -----------------------------
    # Map POIs to 5M and log events
    # -----------------------------
    for poi_idx, poi in enumerate(unique_pois, 1):
        # Align POI time to nearest 5M candle
        nearest_idx = df_5m.index.get_indexer([poi["time"]], method="ffill")[0]
        start_time = df_5m.index[nearest_idx]

        # End time for POI rectangle (4H window)
        end_time = start_time + pd.Timedelta(hours=4)
        if end_time > df_5m.index[-1]:
            end_time = df_5m.index[-1]

        # Select 5M candles for this POI
        mask = (df_5m.index >= start_time) & (df_5m.index <= end_time)
        df_range = df_5m.loc[mask]
        if df_range.empty:
            continue

        mapped = {
            "type": poi["type"],
            "trend": poi["trend"],
            "start_time": df_range.index[0],
            "end_time": df_range.index[-1],
            "leg_start_5m": leg_start_5m,
            "leg_end_5m": leg_end_5m
        }

        if poi["type"] == "OB":
            mapped.update({
                "price_low": poi["price_low"],
                "price_high": poi["price_high"],
            })
            low = poi["price_low"]
            high = poi["price_high"]
            poi_type = "OB"
        elif poi["type"] == "LIQ":
            mapped.update({
                "price": poi["price_low"] if poi["price_low"] is not None else poi["price_high"]
            })
            low = poi["price_low"]
            high = poi["price_high"]
            poi_type = "LIQ"

        mapped_pois.append(mapped)

        # -----------------------------
        # Logging 4H POI (existing)
        # -----------------------------
        trend_upper = poi["trend"].upper()
        if poi_type == "OB":
            reason = "displacement candle confirmed, base candle not broken"
        else:
            reason = "pullback candles met, not tapped yet"

        log_event_master(
            idx=poi_idx,
            time=poi["time"],
            trend=trend_upper,
            event="poi_detected",
            reason=reason,
            poi_type=poi_type,
            poi_low=low,
            poi_high=high,
            candle=None,
        )

        log_event(
            idx=poi_idx,
            t=poi["time"],
            trend=trend_upper,
            event="poi_detected",
            poi_type=poi_type,
            price_low=low,
            price_high=high,
            active_poi=poi,
            validation_tf="4h"
        )

    print(f"{indent}🖌️ POIs mapped and logged: {len(mapped_pois)}")



                    
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
    in_pullback = False
    temp_pullback_high = None
    temp_pullback_low = None


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
                    
                    # Continue to check TP/SL in same iteration
                else:
                    # Entry not filled - check if TP hit without entry
                    if trend == "BULLISH":
                        if c5.high >= trade_details["tp"]:
                            print(f"{indent}🟩 TP HIT WITHOUT ENTRY → TRADE INVALID")
                            
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
                htf_idx = df_4h.index.get_indexer([t5], method="ffill")[0]
                htf_time = df_4h.index[htf_idx]
                reason = "price closed below previous swing low → structure invalidated"

                log_event_master(
                    idx=htf_idx,
                    time=htf_time,
                    trend=trend,
                    event="choch_4h",
                    reason=reason,           # ← reason added
                    swing_low=swing_low,
                    swing_high=None,
                    candle=c5
                )
                log_event(
                    idx=htf_idx,
                    t=htf_time,
                    trend=trend,
                    event="choch_4h",
                    swing_low=swing_low,
                    swing_high=None,
                    validation_tf="4h"
                )

                # trim before swing_high
                df_4h_new = df_4h.loc[df_4h.index >= df_4h.loc[df_4h['high'] == swing_high].index[0]]
                # 🔁 Align 5M with HTF swing HIGH
                swing_high_time = df_4h.loc[df_4h['high'] == swing_high].index[0]
                df_5m_new = df_5m.loc[df_5m.index >= swing_high_time]

                # 1️⃣ Snapshot the leg
                leg_5m_events.append({
                    "event": "leg_end",
                    "trend": trend,
                    "start_time": leg_start_5m,
                    "end_time": t5,
                    "pois": [
                        {
                            "type": p["type"],
                            "price_low": p["price_low"],
                            "price_high": p["price_high"],
                            "state": p.get("state", "UNTOUCHED")
                        }
                        for p in pois
                    ],
                    # ✅ MULTIPLE taps supported
                    "tapped_pois": list(tapped_pois),
                    # ✅ MULTIPLE protected 5M points supported
                    "protected_5m_points": list(protected_5m_points),
                    "choch_bos_events": list(leg_5m_structure),
                    "five_m_obs": list(all_5m_obs),              
                    "planned_trade": list(all_5m_trades)        
                })

                # 2️⃣ Persist the leg
                all_legs_event_logs.append(list(leg_5m_events))
                leg_5m_events.clear()

                return market_structure_mapping(
                    df_4h=df_4h_new,
                    df_5m=df_5m_new,
                    trend="BEARISH",
                    bos_time=t5,
                    depth=depth + 1,
                )

            if trend == "BEARISH" and c5.close > swing_high:
                print(f"{indent}🟥 CHOCH @ {t5} in 4h")
                htf_idx = df_4h.index.get_indexer([t5], method="ffill")[0]
                htf_time = df_4h.index[htf_idx]
                reason = "price closed above previous swing high → structure invalidated"
                log_event_master(
                    idx=htf_idx,
                    time=htf_time,
                    trend=trend,
                    event="choch_4h",
                    reason=reason,           # ← reason added
                    swing_low=None,
                    swing_high=swing_high,
                    candle=c5
                )
                log_event(
                    idx=htf_idx,
                    t=htf_time,
                    trend=trend,
                    event="choch_4h",
                    swing_low=None,
                    swing_high=swing_high,
                    validation_tf="4h"
                )


                df_4h_new = df_4h.loc[df_4h.index >= df_4h.loc[df_4h['low'] == swing_low].index[0]]
                # 🔁 Align 5M with HTF swing HIGH
                swing_low_time = df_4h.loc[df_4h['low'] == swing_low].index[0]
                df_5m_new = df_5m.loc[df_5m.index >= swing_low_time]

                # 1️⃣ Snapshot the leg
                leg_5m_events.append({
                    "event": "leg_end",
                    "trend": trend,
                    "start_time": leg_start_5m,
                    "end_time": t5,
                    "pois": [
                        {
                            "type": p["type"],
                            "price_low": p["price_low"],
                            "price_high": p["price_high"],
                            "state": p.get("state", "UNTOUCHED")
                        }
                        for p in pois
                    ],
                    # ✅ MULTIPLE taps supported
                    "tapped_pois": list(tapped_pois),
                    # ✅ MULTIPLE protected 5M points supported
                    "protected_5m_points": list(protected_5m_points),
                    "choch_bos_events": list(leg_5m_structure),
                    "five_m_obs": list(all_5m_obs),              
                    "planned_trade": list(all_5m_trades)          
                })

                # 2️⃣ Persist the leg
                all_legs_event_logs.append(list(leg_5m_events))
                leg_5m_events.clear()
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
                htf_idx = df_4h.index.get_indexer([t5], method="ffill")[0]
                htf_time = df_4h.index[htf_idx]
                reason = "price closed above previous swing high → BOS triggered without prior POI"

                log_event_master(
                    idx=htf_idx,
                    time=htf_time,
                    trend=trend,
                    event="bos_4h",
                    reason=reason,            # ← reason added
                    swing_high=swing_high,
                    swing_low=None,
                    candle=c5
                )
                        

                log_event(
                    idx=htf_idx,
                    t=htf_time,
                    trend=trend,
                    event="bos_4h",
                    swing_high=swing_high,
                    swing_low=None,
                    validation_tf="4h"
                )
    
                # lowest low from swing_high → BOS
                # 1️⃣ Find the swing high time (timestamp of candle that formed swing high)
                swing_high_time = df_4h.loc[df_4h['high'] == swing_high].index[0]

                # slice from swing_high to BOS
                slice_df = df_4h.loc[swing_high_time:t5]

                if not slice_df.empty:
                    lowest_low_time = slice_df['low'].idxmin()   # safest
                    df_4h_new = df_4h.loc[df_4h.index >= lowest_low_time]
                else:
                    df_4h_new = df_4h.copy()   # fallback

                # 5M — align to SAME swing low time
                start_5m_idx = df_5m.index.get_indexer(
                    [lowest_low_time], method="bfill"
                )[0]

                df_5m_new = df_5m.iloc[start_5m_idx:]
                # 1️⃣ Snapshot the leg
                leg_5m_events.append({
                    "event": "leg_end",
                    "trend": trend,
                    "start_time": leg_start_5m,
                    "end_time": t5,
                    "pois": [
                        {
                            "type": p["type"],
                            "price_low": p["price_low"],
                            "price_high": p["price_high"],
                            "state": p.get("state", "UNTOUCHED")
                        }
                        for p in pois
                    ],
                    # ✅ MULTIPLE taps supported
                    "tapped_pois": list(tapped_pois),
                    # ✅ MULTIPLE protected 5M points supported
                    "protected_5m_points": list(protected_5m_points),
                    "choch_bos_events": list(leg_5m_structure) ,
                    "five_m_obs": list(all_5m_obs),              
                    "planned_trade": list(all_5m_trades)         
                })

                # 2️⃣ Persist the leg
                all_legs_event_logs.append(list(leg_5m_events))
                leg_5m_events.clear()
                
                return market_structure_mapping(
                    df_4h=df_4h_new,
                    df_5m=df_5m_new,
                    trend="BULLISH",
                    bos_time=t5,
                    depth=depth + 1,
                )

            if trend == "BEARISH" and c5.close < swing_low:
                print(f"{indent}🟦 BOS WITHOUT POI @ {t5} in 4h")
                htf_idx = df_4h.index.get_indexer([t5], method="ffill")[0]
                htf_time = df_4h.index[htf_idx]
                reason = "price closed below previous swing low → BOS triggered without prior POI"

                log_event_master(
                    idx=htf_idx,
                    time=htf_time,
                    trend=trend,
                    event="bos_4h",
                    reason=reason,            # ← reason added
                    swing_high=None,
                    swing_low=swing_low,
                    candle=c5
                )

                log_event(
                    idx=htf_idx,
                    t=htf_time,
                    trend=trend,
                    event="bos_4h",
                    swing_high=None,
                    swing_low=swing_low,
                    validation_tf="4h"
                )

            
                # 1️⃣ Find the swing low time (timestamp of candle that formed swing low)
                swing_low_time = df_4h.loc[df_4h['low'] == swing_low].index[0]
                # slice from swing_low to BOS
                slice_df = df_4h.loc[swing_low_time:t5]

                if not slice_df.empty:
                    highest_high_time = slice_df['high'].idxmax()
                    df_4h_new = df_4h.loc[df_4h.index >= highest_high_time]
                else:
                    df_4h_new = df_4h.copy()   # fallback


                # 1️⃣ Find the swing low time (timestamp of candle that formed swing low)
                swing_low_time = df_4h.loc[df_4h['low'] == swing_low].index[0]
                # slice from swing_low to BOS
                slice_df = df_4h.loc[swing_low_time:t5]

                if not slice_df.empty:
                    highest_high_time = slice_df['high'].idxmax()
                    df_4h_new = df_4h.loc[df_4h.index >= highest_high_time]
                else:
                    df_4h_new = df_4h.copy()   # fallback


                # ✅ Refine 5M as well (usual)
                df_5m_new = df_5m.loc[df_5m.index >= t5]   # t5 = BOS time

                # 1️⃣ Snapshot the leg
                leg_5m_events.append({
                    "event": "leg_end",
                    "trend": trend,
                    "start_time": leg_start_5m,
                    "end_time": t5,
                    "pois": [
                        {
                            "type": p["type"],
                            "price_low": p["price_low"],
                            "price_high": p["price_high"],
                            "state": p.get("state", "UNTOUCHED")
                        }
                        for p in pois
                    ],
                    # ✅ MULTIPLE taps supported
                    "tapped_pois": list(tapped_pois),
                    # ✅ MULTIPLE protected 5M points supported
                    "protected_5m_points": list(protected_5m_points),
                    "choch_bos_events": list(leg_5m_structure),
                    "five_m_obs": list(all_5m_obs),              
                    "planned_trade": list(all_5m_trades)        
                })
                # 2️⃣ Persist the leg
                all_legs_event_logs.append(list(leg_5m_events))
                leg_5m_events.clear()            
                                
                return market_structure_mapping( 
                    df_4h=df_4h_new,
                    df_5m=df_5m_new,
                    trend="BEARISH",
                    bos_time=t5,
                    depth=depth + 1,
                )
      
        # --------------------------------------------------
        # 3️⃣ POI TAP (TREND + TYPE BASED)
        # --------------------------------------------------
        if not poi_active:
            active_poi = next((p for p in pois if p.get("state") != "INVALIDATED"), None)
            if not active_poi:
                continue
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
                active_poi["activation_time"] = t5
                active_poi["activation_idx"] = df_5m.index.get_indexer(
                    [t5], method="nearest"
                )[0]

                print(f"{indent}🔥 POI TAPPED ({poi_type}) @ {t5}")
                poi_time_4h = active_poi["time"]
                poi_5m_idx = df_5m.index.get_indexer([poi_time_4h], method="bfill")[0]
                active_poi["start_5m_time"] = df_5m.index[poi_5m_idx]
                tapped_pois.append({
                    "type": poi_type,
                    "price_low": poi_low,
                    "price_high": poi_high,
                    "tap_time": t5
                })
                
                # 🔹 CALL 5M STRUCTURE FUNCTION HERE
                opp_trend = "BEARISH" if trend == "BULLISH" else "BULLISH"
                if trend == "BULLISH":
                    swing_high_time = df_4h.loc[df_4h['high'] == swing_high].index[0]
                    m5_slice = df_5m.loc[swing_high_time:t5]
                else:
                    swing_low_time = df_4h.loc[df_4h['low'] == swing_low].index[0]
                    m5_slice = df_5m.loc[swing_low_time:t5]

                protected_5m_point = process_structure_and_return_last_swing(
                    df=m5_slice,
                    trend=opp_trend,
                )
                protected_5m_time = t5
                # Check if return value is valid (not None and not 0.0 or negative)
                if protected_5m_point is None or protected_5m_point <= 0:
                    print(f"{indent}❌ Invalid 5M structure point: {protected_5m_point}")
                    poi_active = False
                    protected_5m_point = None
                    continue
                print(f"{indent}✅ 5M Protected Point: {protected_5m_point}")
                # whenever you detect a protected 5M point:
                if protected_5m_point is not None:
                    protected_5m_points.append({
                        "t": t5,
                        "trend": trend.upper(),
                        "event": "protected_5m_point",
                        "poi_type": "STRUCTURE",
                        "price_low": protected_5m_point,
                        "price_high": protected_5m_point
                    })
                    print(f"{indent}📌 5M Protected Point logged: {protected_5m_point}")
                else:
                    print(f"{indent}❌ Invalid 5M structure point: {protected_5m_point}")
                    poi_active = False
                    protected_5m_point = None
                    continue
        # --------------------------------------------------
        # POI INVALIDATION (TYPE + ORDER AWARE)
        # --------------------------------------------------
        if poi_active and active_poi:

            current_idx = df_5m.index.get_indexer([t5], method="nearest")[0]
            # ⛔ DO NOT invalidate on the tap candle
            if current_idx <= active_poi["activation_idx"]:
                pass
            else:
                valid_pois = [p for p in pois if p.get("state") != "INVALIDATED"]
                if active_poi not in valid_pois:
                    continue
                idx0 = valid_pois.index(active_poi)
                next_poi = valid_pois[idx0 + 1] if idx0 + 1 < len(valid_pois) else None


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
                        
                        if active_poi:
                            active_poi["state"] = "INVALIDATED"
                            poi_active = False
                            active_poi = None
                            poi_tapped = False
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

                    
                        if active_poi:
                            active_poi["state"] = "INVALIDATED"
                            poi_active = False
                            active_poi = None
                            poi_tapped = False
                            protected_5m_point = None
                            continue

                
        # --------------------------------------------------
        # 5️⃣ 5M STRUCTURE CHECK (CHOCH / BOS LOGIC)
        # --------------------------------------------------
        if protected_5m_point is not None:
            if trend == "BULLISH":
                # opp_trend is BEARISH, so protected_5m_point is a SWING HIGH
                # CHOCH = break above swing high
                if c5.close > protected_5m_point:
                    broken_level = protected_5m_point
                    choch_validated = True
                    poi_active = False
                    if active_poi:
                        active_poi["state"] = "INVALIDATED"
                        active_poi = None
                        poi_tapped = False
                        
                    protected_5m_point = None
                    swing_low_5m = None
                    swing_high_5m = None
                    swing_low_range_start = None
                    swing_high_range_start = None

                    in_pullback = False
                    temp_pullback_high = None
                    temp_pullback_low = None
                    opp_pullback_count = 0   

                elif c5.close > c5.open and swing_low_5m is None and not choch_validated:
                    # GREEN candle = pullback candle in bearish leg
                    if not in_pullback:
                        in_pullback = True
                        opp_pullback_count = 1
                        temp_pullback_high = c5.high
                        temp_pullback_low = c5.low
                    else:
                        opp_pullback_count += 1
                        temp_pullback_high = max(temp_pullback_high, c5.high)
                        temp_pullback_low = min(temp_pullback_low, c5.low)

                    print("5m opp pullback count (bullish leg) with time", opp_pullback_count, t5)

                # ❌ INVALID pullback → bearish continuation before confirmation
                elif in_pullback and c5.low < temp_pullback_low and opp_pullback_count < 2:
                    in_pullback = False
                    opp_pullback_count = 0
                    temp_pullback_high = None
                    temp_pullback_low = None

                # ----------------------------------------------
                # 3️⃣ Pullback CONFIRMED → calculate swing LOW
                # ----------------------------------------------
                if (
                    opp_pullback_count == 2 and swing_low_5m is None
                ):
                    # calculate swing low between protected swing high and pullback candle
                    swing_low_range_start = protected_5m_time

                    swing_low_5m = df_5m.loc[
                        swing_low_range_start:t5, "low"
                    ].min()
                    print("calculated swing low 5m:", swing_low_5m)
                # ----------------------------------------------
                # 4️⃣ BOS = break below calculated swing LOW
                # ----------------------------------------------
                if swing_low_5m is not None and c5.low <swing_low_5m:
                    bos_time = t5
                    print("5m BOS time:", bos_time)
                    leg_5m_structure.append({
                        "event": "BOS",
                        "t": bos_time,
                        "price": c5.low,
                        "trend": "BEARISH"
                    })
                    
                    # ------------------------------------------
                    # 5️⃣ UPDATE protected swing HIGH
                    # ------------------------------------------
                    new_protected_high = df_5m.loc[
                        swing_low_range_start:bos_time, "high"
                    ].max()

                    protected_5m_point = new_protected_high
                    protected_5m_time = bos_time
                    print("new protected 5m point (swing high):", protected_5m_point)
                    protected_5m_points.append({
                        "t": t5,
                        "trend": trend.upper(),
                        "event": "protected_5m_point",
                        "poi_type": "STRUCTURE",
                        "price_low": protected_5m_point,
                        "price_high": protected_5m_point
                    })
                    # reset for next structure cycle
                    opp_pullback_count = 0
                    swing_low_5m = None
                    swing_low_range_start = None

                    in_pullback = False
                    temp_pullback_high = None
                    temp_pullback_low = None
                  
            else:
                # opp_trend is BULLISH, so protected_5m_point is a SWING LOW
                # CHOCH = break below swing low
                if c5.close < protected_5m_point:
                    broken_level = protected_5m_point
                    choch_validated = True
                    poi_active = False
                    if active_poi:
                        active_poi["state"] = "INVALIDATED"
                        active_poi = None
                        poi_tapped = False

                    protected_5m_point = None
                    swing_low_5m = None
                    swing_high_5m = None
                    swing_low_range_start = None
                    swing_high_range_start = None

                    in_pullback = False
                    temp_pullback_high = None
                    temp_pullback_low = None
                    opp_pullback_count = 0
                                
                elif c5.close < c5.open and swing_high_5m is None and not choch_validated:
                    # RED candle = pullback candle in bullish leg
                    if not in_pullback:
                        in_pullback = True
                        opp_pullback_count = 1
                        temp_pullback_high = c5.high
                        temp_pullback_low = c5.low
                    else:
                        opp_pullback_count += 1
                        temp_pullback_high = max(temp_pullback_high, c5.high)
                        temp_pullback_low = min(temp_pullback_low, c5.low)

                    print("5m opp pullback count (bullish leg) with time", opp_pullback_count, t5)

                # ❌ INVALID pullback → bullish continuation before confirmation
                elif in_pullback and c5.high > temp_pullback_high and opp_pullback_count < 2:
                    in_pullback = False
                    opp_pullback_count = 0
                    temp_pullback_high = None
                    temp_pullback_low = None

                # ----------------------------------------------
                # 3️⃣ Pullback CONFIRMED → calculate swing HIGH
                # ----------------------------------------------
                if (
                    opp_pullback_count == 2 and swing_high_5m is None
                ):
                    # find candle where protected swing LOW was formed
                    swing_high_range_start = protected_5m_time

                    swing_high_5m = df_5m.loc[
                        swing_high_range_start:t5, "high"
                    ].max()
                    print("calculated swing high 5m:", swing_high_5m)

                # ----------------------------------------------
                # 4️⃣ BOS = break above calculated swing HIGH
                # ----------------------------------------------
                if swing_high_5m is not None and c5.high > swing_high_5m:
                    bos_time = t5
                    print("5m BOS time:", bos_time)

                    leg_5m_structure.append({
                        "event": "BOS",
                        "t": bos_time,
                        "price": c5.high,
                        "trend": "BULLISH"
                    })
                    
                    # ------------------------------------------
                    # 5️⃣ UPDATE protected swing LOW
                    # ------------------------------------------
                    new_protected_low = df_5m.loc[
                        swing_high_range_start:bos_time, "low"
                    ].min()

                    protected_5m_point = new_protected_low
                    protected_5m_time = bos_time   # 🔴 REQUIRED

                    print("new protected 5m point (swing low):", protected_5m_point)
                    protected_5m_points.append({
                        "t": t5,
                        "trend": trend.upper(),
                        "event": "protected_5m_point",
                        "poi_type": "STRUCTURE",
                        "price_low": protected_5m_point,
                        "price_high": protected_5m_point
                    })

                    # reset for next structure cycle
                    opp_pullback_count = 0
                    swing_high_5m = None
                    swing_high_range_start = None

                    in_pullback = False
                    temp_pullback_high = None
                    temp_pullback_low = None
        # ---------------------------
        # Append CHOCH/BOS to structure list
        # ---------------------------
        if choch_validated:
            leg_5m_structure.append({
                "event": "CHOCH",
                "t": t5,
                "price": broken_level,
                "trend": trend.upper()
            })
            

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

            trade,all_obs = plan_trade_from_choch_leg(
                choch_leg_df=choch_leg_df,
                trend=trend,
            )
            choch_validated = False
            print(trade)

            if trade:
                # ✅ Store all OBs and trade info globally
                all_5m_obs.append({
                    "choch_leg_start": choch_leg_start,
                    "choch_leg_end": t5,
                    "trend": trend,
                    "ob_time": trade["ob_time"],
                    "ob_high": trade["ob_high"],
                    "ob_low": trade["ob_low"]
                })
                all_5m_trades.append({
                    "choch_leg_start": choch_leg_start,
                    "choch_leg_end": t5,
                    "trend": trend,
                    "entry": trade["entry"],
                    "sl": trade["sl"],
                    "tp": trade["tp"],
                    "direction": trade["direction"],
                    "ob_time": trade["ob_time"],
                    "ob_high": trade["ob_high"],
                    "ob_low": trade["ob_low"]
                })

                # -------------------------------
                # TP VALIDATION AGAINST HTF SWING
                # -------------------------------
                if trend == "BULLISH" and trade["tp"] >= swing_high:
                    print(f"{indent}❌ TP ABOVE SWING HIGH → TRADE REJECTED")
                   

                    choch_validated = False
                    continue

                if trend == "BEARISH" and trade["tp"] <= swing_low:
                    print(f"{indent}❌ TP BELOW SWING LOW → TRADE REJECTED")
                    

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
                

            else:
                print(f"{indent}❌ Trade logic rejected")
                choch_validated = False
    all_legs_event_logs.append(list(leg_5m_events))
    leg_5m_events.clear()  # ready for next leg

    return EVENT_LOG
