from datetime import datetime
from pathlib import Path
import csv
import pandas as pd

import asyncio
from ws.manager import ws_manager

from backend.engine1.registry import StateRegistry
from backend.engine.poi_detection import detect_pois_from_swing 

global event_loop

event_loop = None
# ==================================================
# SIMPLE CANDLE OBJECT
# ==================================================
class Candle:
    def __init__(self, time, open_, high, low, close):
        self.time = time
        self.open = open_
        self.high = high
        self.low = low
        self.close = close

MAX_CANDLES_PER_SECOND = 1
MIN_INTERVAL = 1 / MAX_CANDLES_PER_SECOND 
# ==================================================
# CONFIG
# ==================================================
MINUTE_CSV_PATH = Path(
    r"C:\Gurukiran\projects\trading_system\trading_system_backend\HISTDATA_COM_MT_EURUSD_M12022\DAT_MT_EURUSD_M1_2022.csv"
)

# Buffers
bucket_5m = []
buffer_5m = []  # Holds completed 5M candles
buffer_5m_poi = []       # NEW: only for POI mapping (cleared after poi mapping)
leg_buffer_4h = []     # Holds 4H candles from BOS → pullback
# ==================================================
# STATE REGISTRY SETUP
# ==================================================


registry = StateRegistry()
SYMBOL = "EURUSD"  # Example symbol for now (single pair)
state = registry.get_state(SYMBOL)  # Access the persistent state for this pair

# Set pullback params in state (these can later be config-driven)
state.pullback_pct = 0.02
state.min_pullback_candles = 2
# ==================================================
# SEED / BOOTSTRAP (HISTORICAL CONTEXT)
# ==================================================
# 🔥 This is MANUAL / OFFLINE / HISTORICAL
# No seed logic runs in realtime

state.trend_4h = "BULLISH"

state.swing_low = 1.0820        # last confirmed HL
state.swing_high = None          # NOT known yet
state.bos_level_4h = 1.0945      # price level that caused BOS
state.bos_time_4h = datetime(2023, 3, 10, 8, 0)

# Runtime trackers
state.candidate_high = None
state.candidate_low = None

state.pullback_confirmed = False
state.pullback_time = None

state.bearish_count = 0
state.bullish_count = 0

def reset_on_4h_structure(state):
    # -----------------------------
    # POI state
    # -----------------------------
    state.mapped_pois = []
    state.active_poi = None
    state.poi_tapped = False
    state.poi_tapped_level = None
    state.poi_tapped_time = None

    # -----------------------------
    # 5M structure state
    # -----------------------------
    state.trend_5m = None

    state.swing_high_5m = None
    state.swing_high_5m_time = None
    state.swing_low_5m = None
    state.swing_low_5m_time = None

    state.candidate_high_5m = None
    state.candidate_low_5m = None
    state.pullback_count_5m = 0

    state.buffer_5m_sh.clear()
    state.buffer_5m_sl.clear()

    # -----------------------------
    # 5M protected point
    # -----------------------------
    state.protected_5m_point = None
    state.protected_5m_time = None

    # -----------------------------
    # Clear 4H → 5M mapping buffers
    # -----------------------------
    state.active_pois = []

    state.trade = None
    state.trade_planned = False
    state.entry_filled = False


# ==================================================
# MAIN
# ==================================================
def main():
    # wait until FastAPI sets event_loop
    import time
    while event_loop is None:
        time.sleep(0.05)

    print("=" * 60)
    print("Trading Agent - REALTIME MODE (CSV STREAM)")
    print("=" * 60)

    with open(MINUTE_CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.reader(f)

        for row in reader:
            if len(row) < 6:
                continue

            date_str, time_str, o, h, l, c = row[:6]
            time.sleep(MIN_INTERVAL)
            try:
                t = datetime.strptime(date_str + " " + time_str, "%Y.%m.%d %H:%M")
                candle_1m = Candle(
                    time=t,
                    open_=float(o),
                    high=float(h),
                    low=float(l),
                    close=float(c)
                )
                bucket_5m.append(candle_1m)

                # -----------------------------
                # 1. Build 5M candle incrementally
                # -----------------------------
                # ---------------- 5M CANDLE ----------------
                if len(bucket_5m) == 5:
                    candle_5m = {
                        "time": bucket_5m[0].time,
                        "open": bucket_5m[0].open,
                        "high": max(c.high for c in bucket_5m),
                        "low": min(c.low for c in bucket_5m),
                        "close": bucket_5m[-1].close,
                    }
                    if event_loop is not None:
                        asyncio.run_coroutine_threadsafe(
                            ws_manager.send({
                                "type": "candle",
                                "symbol": "EURUSD",
                                "tf": "5m",
                                "timestamp": int(bucket_5m[0].time.timestamp() * 1000),
                                "open": bucket_5m[0].open,
                                "high": max(c.high for c in bucket_5m),
                                "low": min(c.low for c in bucket_5m),
                                "close": bucket_5m[-1].close,
                            }),
                            event_loop
                        )


                    # Clear 5m bucket
                    buffer_5m.append(candle_5m)
                    bucket_5m.clear()


                # ---------------- 4H CANDLE ----------------
                if len(buffer_5m) == 48:  # 48 × 5m = 4h
                    candle_4h = {
                        "time": buffer_5m[0]["time"],
                        "open": buffer_5m[0]["open"],
                        "high": max(c["high"] for c in buffer_5m),
                        "low": min(c["low"] for c in buffer_5m),
                        "close": buffer_5m[-1]["close"],
                    }

                    if event_loop is not None:
                        asyncio.run_coroutine_threadsafe(
                            ws_manager.send({
                                "type": "candle",
                                "symbol": "EURUSD",
                                "tf": "4h",
                                "timestamp": int(buffer_5m[0]["time"].timestamp() * 1000),
                                "open": buffer_5m[0]["open"],
                                "high": max(c["high"] for c in buffer_5m),
                                "low": min(c["low"] for c in buffer_5m),
                                "close": buffer_5m[-1]["close"],
                            }),
                            event_loop
                        )

                    # Clear 4h buffer
                    buffer_5m.clear()
  

                    # --------------------------------------------------
                    # 2. BUILD 4H CANDLE
                    # --------------------------------------------------
                    if len(buffer_5m) == 48:
                        candle_4h = {
                            "time": buffer_5m[0]["time"],
                            "open": buffer_5m[0]["open"],
                            "high": max(c["high"] for c in buffer_5m),
                            "low": min(c["low"] for c in buffer_5m),
                            "close": buffer_5m[-1]["close"],
                        }
                        if event_loop is not None:
                            event_loop.call_soon_threadsafe(
                                asyncio.create_task,
                                ws_manager.send({
                                    "symbol": "EURUSD",
                                    "tf": "4h",
                                    "time": int(buffer_5m[0]["time"].timestamp() * 1000),
                                    "open": buffer_5m[0]["open"],
                                    "high": max(c["high"] for c in buffer_5m),
                                    "low": min(c["low"] for c in buffer_5m),
                                    "close": buffer_5m[-1]["close"],
                                })
                            )




                        buffer_5m.clear()

                        # --------------------------------------------------
                        # IGNORE HISTORICAL (PRE-BOS)
                        # --------------------------------------------------
                        if candle_4h["time"] <= state.bos_time_4h:
                            continue

                        leg_buffer_4h.append(candle_4h)
                        # -----------------------------
                        # 3A. Update Pullback State
                        # ----------------------------- 

                        if state.trend_4h == "BULLISH":
                            if state.candidate_high is None or candle_4h["high"] > state.candidate_high:
                                state.candidate_high = candle_4h["high"]
                                state.bearish_count = 0

                            if candle_4h["close"] < candle_4h["open"] and candle_4h["high"] < state.candidate_high:
                                state.bearish_count += 1

                            if state.swing_low and state.candidate_high:
                                depth_ratio = (state.candidate_high - min(candle_4h["low"], candle_4h["close"])) / max(state.candidate_high - state.swing_low, 1e-9)
                                if state.bearish_count >= state.min_pullback_candles or depth_ratio >= state.pullback_pct:
                                    state.pullback_confirmed = True
                                    state.pullback_time = candle_4h["time"]
                                    state.h4_structure_event=None
                                    state.swing_high = state.candidate_high
                                    state.candidate_high = None
                                    state.bearish_count = 0

                                    #Call POI detection after pullback
                                    swing_df = pd.DataFrame(leg_buffer_4h)
                                    state.active_pois = detect_pois_from_swing(
                                        ohlc_df=swing_df,
                                        trend=state.trend_4h
                                    )
                                    # Deduplicate POIs
                                    seen = set()
                                    unique_pois = []
                                    for poi in state.active_pois:
                                        key = (poi["time"], poi.get("price_low"), poi.get("price_high"), poi["type"])
                                        if key not in seen:
                                            seen.add(key)
                                            unique_pois.append(poi)

                                    mapped_pois = []

                                    # Map POIs to 5M candles in leg_buffer_4h
                                    for poi in unique_pois:
                                        nearest_candle = None
                                        for c in buffer_5m_poi:
                                            if c["time"] <= poi["time"]:
                                                nearest_candle = c
                                            else:
                                                break
                                        if nearest_candle is None:
                                            nearest_candle = buffer_5m_poi[0]

                                        start_time = nearest_candle["time"]
                                        end_time = start_time + pd.Timedelta(hours=4)
                                        if end_time > buffer_5m_poi[-1]["time"]:
                                            end_time = buffer_5m_poi[-1]["time"]

                                        mapped = {
                                            "type": poi["type"],
                                            "trend": poi["trend"],
                                            "start_time": start_time,
                                            "end_time": end_time,
                                            "leg_start_5m": leg_buffer_4h[0]["time"],    # first candle in leg
                                            "leg_end_5m": leg_buffer_4h[-1]["time"]      # last candle in leg
                                        }

                                        if poi["type"] == "OB":
                                            mapped.update({
                                                "price_low": poi["price_low"],
                                                "price_high": poi["price_high"],
                                            })
                                        elif poi["type"] == "LIQ":
                                            mapped.update({
                                                "price": poi["price_low"] if poi["price_low"] is not None else poi["price_high"]
                                            })

                                        mapped_pois.append(mapped)

                                    # Save mapped POIs to state
                                    state.mapped_pois = mapped_pois
                                    # Clear POI-specific 5M buffer for next leg
                                    buffer_5m_poi.clear()

                                    # --------------------------------------------------
                                    #  CHECK FOR CHOCH (STRUCTURE BREAK)
                                    # --------------------------------------------------
                                    if state.pullback_confirmed:
                                        # Bearish CHOCH → price closes below last swing_low
                                        if state.swing_low and candle_4h["close"] < state.swing_low:
                                            print(f"🟥 BEARISH CHOCH @ {candle_4h['time']} in BULLISH trend")
                                            # Save CHOCH info
                                            state.bos_time_4h = candle_4h["time"]
                                            state.choch_level_4h = candle_4h["close"]
                                            state.h4_structure_event = "CHOCH"
                                            reset_on_4h_structure(state)
                                            state.swing_high = state.candidate_high
                                            state.candidate_high = None
                                            # Reset broken swing
                                            state.swing_low = None
                                            # Start new candidate_low for next pullback
                                            state.candidate_low = candle_4h["low"]
                                            # Flip trend
                                            state.trend_4h = "BEARISH"
                                            # Reset pullback tracking for new trend
                                            state.pullback_confirmed = False
                                            state.pullback_time = None
                                            state.bullish_count = 0
                                            state.bearish_count = 0
                                            buffer_5m.clear()  
                                            leg_buffer_4h.clear()
                                    # -----------------------------
                                    #  BOS WITHOUT POI (Realtime)
                                    # -----------------------------
                                    poi_active = bool(state.mapped_pois)  # Equivalent to old batch "poi_active"

                                    if state.pullback_confirmed and not poi_active:
                                        # -----------------------------
                                        # BULLISH TREND BOS WITHOUT POI
                                        # -----------------------------
                                        if state.trend_4h == "BULLISH" and candle_4h["close"] > state.swing_high:
                                            print(f"🟦 BOS WITHOUT POI @ {candle_4h['time']} in 4H")
                                            state.bos_level_4h = candle_4h["close"]
                                            state.bos_time_4h= candle_4h["time"]
                                            state.h4_structure_event="BOS"
                                            reset_on_4h_structure(state)                
                                            # 🔹 Calculate new swing LOW from old leg
                                            state.swing_low= min(c["low"] for c in leg_buffer_4h)
                                            
                                            # Trim buffers so the next leg starts fresh
                                            leg_buffer_4h.clear()
                                            buffer_5m.clear()


                        elif state.trend_4h == "BEARISH":
                            if state.candidate_low is None or candle_4h["low"] < state.candidate_low:
                                state.candidate_low = candle_4h["low"]
                                state.bullish_count = 0

                            if candle_4h["close"] > candle_4h["open"] and candle_4h["low"] > state.candidate_low:
                                state.bullish_count += 1

                            if state.swing_high and state.candidate_low:
                                depth_ratio = (candle_4h["high"] - state.candidate_low) / max(state.swing_high - state.candidate_low, 1e-9)
                                if state.bullish_count >= state.min_pullback_candles or depth_ratio >= state.pullback_pct:
                                    state.pullback_confirmed = True
                                    state.pullback_time = candle_4h["time"]
                                    state.h4_structure_event=None
                                    state.swing_low = state.candidate_low
                                    state.bullish_count = 0

                                    #Call POI detection after pullback
                                    swing_df = pd.DataFrame(leg_buffer_4h)
                                    state.active_pois = detect_pois_from_swing(
                                        ohlc_df=swing_df,
                                        trend=state.trend_4h
                                    )

                                    # Deduplicate POIs
                                    seen = set()
                                    unique_pois = []
                                    for poi in state.active_pois:
                                        key = (poi["time"], poi.get("price_low"), poi.get("price_high"), poi["type"])
                                        if key not in seen:
                                            seen.add(key)
                                            unique_pois.append(poi)

                                    mapped_pois = []

                                    # Map POIs to 5M candles in buffer_5m_poi
                                    for poi in unique_pois:
                                        nearest_candle = None
                                        for c in buffer_5m_poi:
                                            if c["time"] <= poi["time"]:
                                                nearest_candle = c
                                            else:
                                                break
                                        if nearest_candle is None:
                                            nearest_candle = buffer_5m_poi[0]

                                        start_time = nearest_candle["time"]
                                        end_time = start_time + pd.Timedelta(hours=4)
                                        if end_time > buffer_5m_poi[-1]["time"]:
                                            end_time = buffer_5m_poi[-1]["time"]

                                        mapped = {
                                            "type": poi["type"],
                                            "trend": poi["trend"],
                                            "start_time": start_time,
                                            "end_time": end_time,
                                            "leg_start_5m": leg_buffer_4h[0]["time"],  # first candle in leg
                                            "leg_end_5m": leg_buffer_4h[-1]["time"],   # last candle in leg
                                        }

                                        if poi["type"] == "OB":
                                            mapped.update({
                                                "price_low": poi["price_low"],
                                                "price_high": poi["price_high"],
                                            })
                                        elif poi["type"] == "LIQ":
                                            mapped.update({
                                                "price": poi["price_low"] if poi["price_low"] is not None else poi["price_high"]
                                            })

                                        mapped_pois.append(mapped)

                                    # Save mapped POIs to state
                                    state.mapped_pois = mapped_pois
                                    # Clear POI-specific 5M buffer for next leg
                                    buffer_5m_poi.clear()

                                    # --------------------------------------------------
                                    # 4️⃣ CHECK FOR CHOCH (STRUCTURE BREAK)
                                    # --------------------------------------------------
                                    if state.pullback_confirmed:
                                        if state.swing_high and candle_4h["close"] > state.swing_high:
                                            print(f"🟩 BULLISH CHOCH @ {candle_4h['time']} in BEARISH trend")
                                            # Save CHOCH info
                                            state.bos_time_4h = candle_4h["time"]
                                            state.choch_level_4h = candle_4h["close"]
                                            state.h4_structure_event="CHOCH"
                                            reset_on_4h_structure(state)
                                            state.swing_high = None
                                            state.candidate_high = candle_4h["high"]
                                            state.trend_4h = "BULLISH"
                                            # Reset pullback tracking for new trend
                                            state.pullback_confirmed = False
                                            state.pullback_time = None
                                            state.bullish_count = 0
                                            state.bearish_count = 0
                                            buffer_5m.clear()  
                                            leg_buffer_4h.clear()
                                    # -----------------------------
                                    #  BOS WITHOUT POI (Realtime)
                                    # -----------------------------
                                    poi_active = bool(state.mapped_pois)  # Equivalent to old batch "poi_active"

                                    if state.pullback_confirmed and not poi_active:
                                        # -----------------------------
                                        # BULLISH TREND BOS WITHOUT POI
                                        # -----------------------------
                                        if state.trend_4h == "BEARISH" and candle_4h["close"] < state.swing_low:
                                            print(f"🟦 BOS WITHOUT POI @ {candle_4h['time']} in 4H")
                                            state.bos_level_4h = candle_4h["close"]
                                            state.bos_time_4h = candle_4h["time"]
                                            state.h4_structure_event="BOS"
                                            reset_on_4h_structure(state)
                                            # 🔹 New swing HIGH from previous leg
                                            state.swing_high = max(c["high"] for c in leg_buffer_4h)
                                            
                                            # Trim buffers so the next leg starts fresh
                                            leg_buffer_4h.clear()
                                            buffer_5m.clear()

                    # --------------------------------------------------
                    # 5M GATING LOGIC
                    # --------------------------------------------------

                    # ❌ Gate 1: Ignore all 5M candles until 4H pullback is confirmed
                    if not state.pullback_confirmed:
                        continue
                    # ❌ Gate 2: Ignore 5M candles before pullback time
                    elif state.pullback_time and candle_5m["time"] < state.pullback_time:
                        continue
                    # ❌ Gate 3: Stop 5M processing immediately on 4H BOS / CHOCH
                    elif state.h4_structure_event in ("BOS", "CHOCH"):
                        continue   
                    bull_candle_5m = candle_5m["close"] > candle_5m["open"]
                    bear_candle_5m = candle_5m["close"] < candle_5m["open"]
                    
                    if state.trend_4h == "BULLISH":
                        state.trend_5m = "BEARISH"

                        if state.candidate_low_5m is None:
                            state.candidate_low_5m = candle_5m["low"]
                            state.pullback_count_5m = 0
                            if state.swing_high_5m is None:
                                state.swing_high_5m = candle_5m["high"]
                                state.swing_high_time=candle_5m["time"]
                            continue

                        if bull_candle_5m and (state.pullback_count_5m == 0 or state.pullback_count_5m == 1):
                            state.pullback_count_5m += 1

                        if candle_5m["low"] < state.candidate_low_5m:
                            state.candidate_low_5m = candle_5m["low"]

                        retrace = (candle_5m["high"] - state.candidate_low_5m) / max(state.swing_high_5m - state.candidate_low_5m, 1e-9)
                        valid_pullback_5m = state.pullback_count_5m >= 2 or retrace >= 0.99

                        if valid_pullback_5m:
                            state.buffer_5m_sh.append(candle_5m)    
                            #BOS 5m                        
                            if candle_5m["low"] < state.candidate_low_5m:
                                swing_candle = max(
                                    state.buffer_5m_sh,
                                    key=lambda c: c["high"]
                                )

                                state.swing_high_5m = swing_candle["high"]
                                state.swing_high_5m_time = swing_candle["time"] 
                                state.protected_5m_point = state.swing_high_5m
                                state.protected_5m_time  = state.swing_high_5m_time  
                                
                                state.candidate_low_5m = candle_5m["low"]
                                state.pullback_count_5m=0
                                state.buffer_5m_sh.clear()
                            #CHOCH 5m
                            if candle_5m["high"] > state.swing_high_5m:
                                state.trend_5m = "BULLISH"
                                state.swing_low_5m = state.candidate_low_5m
                                state.pullback_count_5m=0
                                state.candidate_high_5m= candle_5m["high"]
                                choch_5m_this_candle = True
                                state.buffer_5m_sh.clear()
                        # --------------------------------------------------
                        # 5M POI TAP CHECK (Realtime)
                        # --------------------------------------------------
                        if state.mapped_pois and not state.poi_tapped and state.active_poi is None:
                    
                            for poi in state.mapped_pois:
                                if poi_invalidated == False:
                                    continue
                                poi_type = poi["type"]
                                poi_trend = poi["trend"]

                                if poi_trend == "BULLISH":
                                    if poi_type == "OB":
                                        # OB overlap
                                        if candle_5m["low"] <= poi["price_high"] and candle_5m["high"] >= poi["price_low"]:
                                            state.poi_tapped = True
                                            state.active_poi=poi
                                            state.poi_tapped_level=candle_5m["low"]
                                            state.poi_tapped_time=candle_5m["time"]
                                            
                                            break
                                    elif poi_type == "LIQ":
                                        # LIQ sweep
                                        if candle_5m["low"] <= poi["price"]:
                                            state.poi_tapped = True
                                            state.active_poi=poi
                                            state.poi_tapped_level=candle_5m["low"]
                                            state.poi_tapped_time=candle_5m["time"]
                                            
                                            break
                        # POST POI TAP                
                        if state.poi_tapped:

                            # --------------------------------------------------
                            #  POI INVALIDATION (Realtime)
                            # --------------------------------------------------
                            poi_invalidated = False

                            active_poi = state.active_poi

                            # ⛔ Do NOT invalidate on tap candle
                            if candle_5m["time"] > state.poi_tapped_time and state.active_poi:

                                active_poi = state.active_poi
                                invalidation_level = None

                                # Find next POI (order-aware) if it exists
                                next_poi = None
                                for poi in state.mapped_pois:
                                    if poi is active_poi:
                                        continue
                                    if poi.get("state") != "INVALIDATED":
                                        next_poi = poi
                                        break  # first non-invalidated POI after current active POI

                                p0_type = active_poi["type"]
                                trend = state.trend_4h

                                # =========================
                                # BULLISH TREND
                                # =========================
                                if trend == "BULLISH":

                                    if next_poi:
                                        p1_type = next_poi["type"]

                                        if p0_type == "OB" and p1_type == "OB":
                                            invalidation_level = (active_poi["price_high"] + next_poi["price_high"]) / 2

                                        elif p0_type == "OB" and p1_type == "LIQ":
                                            invalidation_level = (active_poi["price_high"] + next_poi["price"]) / 2

                                        elif p0_type == "LIQ" and p1_type == "LIQ":
                                            invalidation_level = (active_poi["price"] + next_poi["price"]) / 2

                                    else:
                                        # No next POI → fallback to 4H swing low
                                        if p0_type == "OB":
                                            invalidation_level = (active_poi["price_high"] + state.swing_low) / 2
                                        else:
                                            invalidation_level = (active_poi["price"] + state.swing_low) / 2

                                    if invalidation_level is not None and candle_5m["low"] < invalidation_level:
                                        poi_invalidated = True
                                        state.active_poi["state"] = "INVALIDATED"
                                
                            # --------------------------------------------------
                            # 🔥 APPLY INVALIDATION
                            # --------------------------------------------------
                            if poi_invalidated:
                                print(f"❌ POI INVALIDATED @ {candle_5m['time']}")

                                state.active_poi["state"] = "INVALIDATED"

                                state.active_poi = None
                                state.poi_tapped = False
                                state.poi_tapped_level = None
                                state.poi_tapped_time = None

                                state.protected_5m_point = None
                                state.protected_5m_time = None

                                continue


                            # --------------------------------------------------
                            # TRADE SETUP (CHOCH + POI)
                            # --------------------------------------------------
                            if (
                                choch_5m_this_candle
                                and state.active_poi is not None
                                and not poi_invalidated
                                and not state.trade_planned
                            ):

                                # ==================================================
                                # DETERMINE RANGE FOR 50% CALCULATION
                                # ==================================================
                                if state.trend_4h == "BULLISH":
                                    # 4H bullish → 5M CHOCH is bullish break
                                    range_high = candle_5m["high"]           # CHOCH candle high
                                    range_low = state.swing_low_5m            # last bearish swing low
                                    direction = "BUY"
                                else:
                                    # 4H bearish → 5M CHOCH is bearish break
                                    range_low = candle_5m["low"]              # CHOCH candle low
                                    range_high = state.swing_high_5m           # last bullish swing high
                                    direction = "SELL"

                                # Safety check
                                if range_high is None or range_low is None:
                                    print("❌ Invalid range — trade skipped")
                                    continue

                                # ==================================================
                                # 50% RETRACEMENT ENTRY
                                # ==================================================
                                entry = (range_high + range_low) / 2

                                pip = 0.0001

                                if direction == "BUY":
                                    stop_loss = range_low - 4 * pip
                                    risk = entry - stop_loss
                                    take_profit = entry + 3 * risk
                                else:
                                    stop_loss = range_high + 4 * pip
                                    risk = stop_loss - entry
                                    take_profit = entry - 3 * risk

                                # Risk validation
                                if risk <= 0:
                                    print("❌ Invalid risk — trade skipped")
                                    continue

                                # ==================================================
                                # STORE TRADE IN STATE (FOR PLOTTING / EXECUTION)
                                # ==================================================
                                state.trade = {
                                    "direction": direction,
                                    "entry": float(entry),
                                    "sl": float(stop_loss),
                                    "tp": float(take_profit),
                                    "rr": 3.0,

                                    # Context
                                    "htf_trend": state.trend_4h,
                                    "poi_type": state.active_poi["type"],
                                    "poi_price_low": state.active_poi.get("price_low"),
                                    "poi_price_high": state.active_poi.get("price_high"),
                                    "poi_time": state.poi_tapped_time,

                                    "choch_time": candle_5m["time"],
                                    "range_high": float(range_high),
                                    "range_low": float(range_low),

                                    # Lifecycle
                                    "planned_time": candle_5m["time"],
                                    "status": "PLANNED",
                                }

                                state.trade_planned = True

                                print("🚀 TRADE PLANNED & STORED")
                                print(f"   Direction : {direction}")
                                print(f"   Entry     : {entry}")
                                print(f"   SL        : {stop_loss}")
                                print(f"   TP        : {take_profit}")


                            # --------------------------------------------------
                            # TRADE MANAGEMENT (BUY ONLY - Realtime 5M)
                            # --------------------------------------------------
                            if state.trade_planned and state.trade is not None:

                                trade = state.trade

                                # Safety: only manage BUY trades here
                                if trade["direction"] != "BUY":
                                    pass
                                else:
                                    entry = trade["entry"]
                                    sl = trade["sl"]
                                    tp = trade["tp"]

                                    candle_high = candle_5m["high"]
                                    candle_low = candle_5m["low"]
                                    candle_time = candle_5m["time"]

                                    # ==================================================
                                    # ENTRY NOT FILLED YET
                                    # ==================================================
                                    if not state.entry_filled:

                                        entry_filled_this_candle = False

                                        # -----------------------------
                                        # ENTRY CHECK FIRST
                                        # -----------------------------
                                        if candle_low <= entry <= candle_high:
                                            entry_filled_this_candle = True

                                        if entry_filled_this_candle:
                                            state.entry_filled = True
                                            trade["status"] = "OPEN"
                                            trade["entry_time"] = candle_time

                                            print(f"🟢 BUY ENTRY FILLED @ {entry} | {candle_time}")

                                        else:
                                            # --------------------------------------------------
                                            # 2% TP MOVE WITHOUT ENTRY → INVALIDATE TRADE
                                            # --------------------------------------------------
                                            tp_2pct_level = entry + 0.02 * (tp - entry)

                                            if candle_high >= tp_2pct_level:
                                                print(
                                                    f"🟩 TP MOVE WITHOUT ENTRY (2% HIT @ {tp_2pct_level}) → TRADE INVALID"
                                                )

                                                # 🔥 RESET TRADE STATE
                                                state.trade = None
                                                state.trade_planned = False
                                                state.entry_filled = False

                                                continue

                                    # ==================================================
                                    # ENTRY FILLED → CHECK SL / TP
                                    # ==================================================
                                    else:

                                        # -----------------------------
                                        # STOP LOSS
                                        # -----------------------------
                                        if candle_low <= sl:
                                            print(f"🟥 BUY SL HIT @ {sl}")

                                            trade["status"] = "SL"
                                            trade["exit_time"] = candle_time
                                            trade["exit_price"] = sl

                                            state.trade = None
                                            state.trade_planned = False
                                            state.entry_filled = False

                                            continue

                                        # -----------------------------
                                        # TAKE PROFIT
                                        # -----------------------------
                                        elif candle_high >= tp:
                                            print(f"🟩 BUY TP HIT @ {tp}")

                                            trade["status"] = "TP"
                                            trade["exit_time"] = candle_time
                                            trade["exit_price"] = tp

                                            state.trade = None
                                            state.trade_planned = False
                                            state.entry_filled = False

                                            continue

                            





                    elif state.trend_4h == "BEARISH":
                        state.trend_5m = "BULLISH"

                        if state.candidate_high_5m is None:
                            state.candidate_high_5m = candle_5m["high"]
                            state.pullback_count_5m = 0
                            if state.swing_low_5m is None:
                                state.swing_low_5m = candle_5m["low"]
                                state.swing_low_5m_time = candle_5m["time"]
                            continue

                        if bear_candle_5m and (state.pullback_count_5m == 0 or state.pullback_count_5m == 1):
                            state.pullback_count_5m += 1

                        if candle_5m["high"] > state.candidate_high_5m:
                            state.candidate_high_5m = candle_5m["high"]

                        retrace = (state.candidate_high_5m - candle_5m["low"]) / max(
                            state.candidate_high_5m - state.swing_low_5m, 1e-9
                        )
                        valid_pullback_5m = state.pullback_count_5m >= 2 or retrace >= 0.99

                        if valid_pullback_5m:
                            state.buffer_5m_sl.append(candle_5m)

                            # BOS 5m
                            if candle_5m["high"] > state.candidate_high_5m:
                                swing_candle = min(
                                    state.buffer_5m_sl,
                                    key=lambda c: c["low"]
                                )

                                state.swing_low_5m = swing_candle["low"]
                                state.swing_low_5m_time = swing_candle["time"]
                                state.protected_5m_point = state.swing_low_5m
                                state.protected_5m_time = state.swing_low_5m_time

                                state.candidate_high_5m = candle_5m["high"]
                                state.pullback_count_5m = 0
                                state.buffer_5m_sl.clear()

                            # CHOCH 5m
                            if candle_5m["low"] < state.swing_low_5m:
                                state.trend_5m = "BEARISH"
                                state.swing_high_5m = state.candidate_high_5m
                                state.pullback_count_5m = 0
                                state.candidate_low_5m = candle_5m["low"]
                                choch_5m_this_candle = True
                                state.buffer_5m_sl.clear()

                        # --------------------------------------------------
                        # 5M POI TAP CHECK (Realtime)
                        # --------------------------------------------------
                        if state.mapped_pois and not state.poi_tapped and state.active_poi is None:

                            for poi in state.mapped_pois:
                                if poi_invalidated == False:
                                    continue

                                poi_type = poi["type"]
                                poi_trend = poi["trend"]

                                if poi_trend == "BEARISH":
                                    if poi_type == "OB":
                                        if candle_5m["high"] >= poi["price_low"] and candle_5m["low"] <= poi["price_high"]:
                                            state.poi_tapped = True
                                            state.active_poi = poi
                                            state.poi_tapped_level = candle_5m["high"]
                                            state.poi_tapped_time = candle_5m["time"]
                                            break

                                    elif poi_type == "LIQ":
                                        if candle_5m["high"] >= poi["price"]:
                                            state.poi_tapped = True
                                            state.active_poi = poi
                                            state.poi_tapped_level = candle_5m["high"]
                                            state.poi_tapped_time = candle_5m["time"]
                                            break
                        # POST POI TAP                
                        if state.poi_tapped:

                            # --------------------------------------------------
                            #  POI INVALIDATION (Realtime)
                            # --------------------------------------------------
                            poi_invalidated = False

                            active_poi = state.active_poi

                            # ⛔ Do NOT invalidate on tap candle
                            if candle_5m["time"] > state.poi_tapped_time and state.active_poi:

                                active_poi = state.active_poi
                                invalidation_level = None

                                # Find next POI (order-aware) if it exists
                                next_poi = None
                                for poi in state.mapped_pois:
                                    if poi is active_poi:
                                        continue
                                    if poi.get("state") != "INVALIDATED":
                                        next_poi = poi
                                        break  # first non-invalidated POI after current active POI

                                p0_type = active_poi["type"]
                                trend = state.trend_4h

                                # =========================
                                # BEARISH TREND
                                # =========================
                                if trend == "BEARISH":

                                    if next_poi:
                                        p1_type = next_poi["type"]

                                        if p0_type == "OB" and p1_type == "OB":
                                            invalidation_level = (active_poi["price_low"] + next_poi["price_low"]) / 2

                                        elif p0_type == "OB" and p1_type == "LIQ":
                                            invalidation_level = (active_poi["price_low"] + next_poi["price"]) / 2

                                        elif p0_type == "LIQ" and p1_type == "LIQ":
                                            invalidation_level = (active_poi["price"] + next_poi["price"]) / 2

                                    else:
                                        # No next POI → fallback to 4H swing high
                                        if p0_type == "OB":
                                            invalidation_level = (active_poi["price_low"] + state.swing_high) / 2
                                        else:
                                            invalidation_level = (active_poi["price"] + state.swing_high) / 2

                                    if invalidation_level is not None and candle_5m["high"] > invalidation_level:
                                        poi_invalidated = True
                                        state.active_poi["state"] = "INVALIDATED"

                            # --------------------------------------------------
                            # 🔥 APPLY INVALIDATION
                            # --------------------------------------------------
                            if poi_invalidated:
                                print(f"❌ POI INVALIDATED @ {candle_5m['time']}")

                                state.active_poi["state"] = "INVALIDATED"

                                state.active_poi = None
                                state.poi_tapped = False
                                state.poi_tapped_level = None
                                state.poi_tapped_time = None

                                state.protected_5m_point = None
                                state.protected_5m_time = None

                                continue


                            # --------------------------------------------------
                            # TRADE SETUP (CHOCH + POI)
                            # --------------------------------------------------
                            if (
                                choch_5m_this_candle
                                and state.active_poi is not None
                                and not poi_invalidated
                                and not state.trade_planned
                            ):

                                # ==================================================
                                # DETERMINE RANGE FOR 50% CALCULATION
                                # ==================================================
                                if state.trend_4h == "BEARISH":
                                    # 4H bearish → 5M CHOCH is bearish break
                                    range_low = candle_5m["low"]              # CHOCH candle low
                                    range_high = state.swing_high_5m           # last bullish swing high
                                    direction = "SELL"
                                else:
                                    # 4H bullish → 5M CHOCH is bullish break
                                    range_high = candle_5m["high"]
                                    range_low = state.swing_low_5m
                                    direction = "BUY"

                                # Safety check
                                if range_high is None or range_low is None:
                                    print("❌ Invalid range — trade skipped")
                                    continue

                                # ==================================================
                                # 50% RETRACEMENT ENTRY
                                # ==================================================
                                entry = (range_high + range_low) / 2

                                pip = 0.0001

                                if direction == "BUY":
                                    stop_loss = range_low - 4 * pip
                                    risk = entry - stop_loss
                                    take_profit = entry + 3 * risk
                                else:
                                    stop_loss = range_high + 4 * pip
                                    risk = stop_loss - entry
                                    take_profit = entry - 3 * risk

                                # Risk validation
                                if risk <= 0:
                                    print("❌ Invalid risk — trade skipped")
                                    continue

                                # ==================================================
                                # STORE TRADE IN STATE (FOR PLOTTING / EXECUTION)
                                # ==================================================
                                state.trade = {
                                    "direction": direction,
                                    "entry": float(entry),
                                    "sl": float(stop_loss),
                                    "tp": float(take_profit),
                                    "rr": 3.0,

                                    # Context
                                    "htf_trend": state.trend_4h,
                                    "poi_type": state.active_poi["type"],
                                    "poi_price_low": state.active_poi.get("price_low"),
                                    "poi_price_high": state.active_poi.get("price_high"),
                                    "poi_time": state.poi_tapped_time,

                                    "choch_time": candle_5m["time"],
                                    "range_high": float(range_high),
                                    "range_low": float(range_low),

                                    # Lifecycle
                                    "planned_time": candle_5m["time"],
                                    "status": "PLANNED",
                                }

                                state.trade_planned = True

                                print("🚀 TRADE PLANNED & STORED")
                                print(f"   Direction : {direction}")
                                print(f"   Entry     : {entry}")
                                print(f"   SL        : {stop_loss}")
                                print(f"   TP        : {take_profit}")


                            # --------------------------------------------------
                            # TRADE MANAGEMENT (SELL ONLY - Realtime 5M)
                            # --------------------------------------------------
                            if state.trade_planned and state.trade is not None:

                                trade = state.trade

                                # Safety: only manage SELL trades here
                                if trade["direction"] != "SELL":
                                    pass
                                else:
                                    entry = trade["entry"]
                                    sl = trade["sl"]
                                    tp = trade["tp"]

                                    candle_high = candle_5m["high"]
                                    candle_low = candle_5m["low"]
                                    candle_time = candle_5m["time"]

                                    # ==================================================
                                    # ENTRY NOT FILLED YET
                                    # ==================================================
                                    if not state.entry_filled:

                                        entry_filled_this_candle = False

                                        # -----------------------------
                                        # ENTRY CHECK FIRST
                                        # -----------------------------
                                        if candle_low <= entry <= candle_high:
                                            entry_filled_this_candle = True

                                        if entry_filled_this_candle:
                                            state.entry_filled = True
                                            trade["status"] = "OPEN"
                                            trade["entry_time"] = candle_time

                                            print(f"🔴 SELL ENTRY FILLED @ {entry} | {candle_time}")

                                        else:
                                            # --------------------------------------------------
                                            # 2% TP MOVE WITHOUT ENTRY → INVALIDATE TRADE
                                            # --------------------------------------------------
                                            tp_2pct_level = entry - 0.02 * (entry - tp)

                                            if candle_low <= tp_2pct_level:
                                                print(
                                                    f"🟥 TP MOVE WITHOUT ENTRY (2% HIT @ {tp_2pct_level}) → TRADE INVALID"
                                                )

                                                # 🔥 RESET TRADE STATE
                                                state.trade = None
                                                state.trade_planned = False
                                                state.entry_filled = False

                                                continue

                                    # ==================================================
                                    # ENTRY FILLED → CHECK SL / TP
                                    # ==================================================
                                    else:

                                        # -----------------------------
                                        # STOP LOSS
                                        # -----------------------------
                                        if candle_high >= sl:
                                            print(f"🟥 SELL SL HIT @ {sl}")

                                            trade["status"] = "SL"
                                            trade["exit_time"] = candle_time
                                            trade["exit_price"] = sl

                                            state.trade = None
                                            state.trade_planned = False
                                            state.entry_filled = False

                                            continue

                                        # -----------------------------
                                        # TAKE PROFIT
                                        # -----------------------------
                                        elif candle_low <= tp:
                                            print(f"🟩 SELL TP HIT @ {tp}")

                                            trade["status"] = "TP"
                                            trade["exit_time"] = candle_time
                                            trade["exit_price"] = tp

                                            state.trade = None
                                            state.trade_planned = False
                                            state.entry_filled = False

                                            continue                                      

            except ValueError:
                continue

# ==================================================
# EXECUTION
# ==================================================
if __name__ == "__main__":
    main()