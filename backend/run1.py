from datetime import datetime
from pathlib import Path
import csv
import pandas as pd
import time

import asyncio
from ws.manager import ws_manager
from ws.event_manager import event_manager

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
state.pullback_pct = 0.35
state.min_pullback_candles = 10
# ==================================================
# SEED / BOOTSTRAP (HISTORICAL CONTEXT)
# ==================================================


state.trend_4h = "BEARISH"

state.swing_low = None       # last confirmed HL
state.swing_high = 1.14827         # NOT known yet
# state.bos_level_4h = 1.0945      # price level that caused BOS
state.bos_time_4h = datetime(2022, 1, 25, 4, 0)

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
    state.swing_low_5m = None
    state.candidate_high_5m = None
    state.candidate_low_5m = None
    state.pullback_count_5m = 0
    state.market_trend_5m = None
    state.choch_5m = False

    state.buffer_5m_sh.clear()
    state.buffer_5m_sl.clear()

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
                    buffer_5m_poi.append(candle_5m)
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
                            if state.pullback_confirmed==False and (state.bearish_count >= state.min_pullback_candles or depth_ratio >= state.pullback_pct):
                                state.pullback_confirmed = True
                                choch_5m=False
                                state.pullback_time = candle_4h["time"]
                                print(f"\n🌊 [4H BULLISH PB] CONFIRMED @ {state.pullback_time}")
                                print(f"   | Reason: {'Count (' + str(state.bearish_count) + ')' if state.bearish_count >= state.min_pullback_candles else 'Depth (' + f'{depth_ratio:.2f}' + ')'}")
                                state.h4_structure_event=None
                                state.swing_high = state.candidate_high

                                if state.pullback_confirmed and state.pullback_time and state.swing_high:
                                    event_payload = {
                                        "symbol": "EURUSD",
                                        "timeframe": "4h",
                                        "events": [
                                            {
                                                "id": f"4H_PB_{state.pullback_time.strftime('%Y%m%d_%H%M')}",
                                                "type": "PULLBACK_CONFIRMED",
                                                "broken_level": state.swing_high,
                                                "time": state.pullback_time.isoformat()
                                            }
                                        ]
                                    }

                                    # Debug print
                                    print(f"📡 Sending 4H Pullback Event: {event_payload}")

                                    if event_loop is not None:
                                        asyncio.run_coroutine_threadsafe(
                                            event_manager.broadcast(event_payload),
                                            event_loop
                                        )

                                state.candidate_high = None
                                state.bearish_count = 0

                                #Call POI detection after pullback
                                swing_df = pd.DataFrame(leg_buffer_4h).set_index("time")
                                state.active_pois = detect_pois_from_swing(
                                    ohlc_df=swing_df,
                                    trend=state.trend_4h
                                )
                                print(f"🔍 DETECTED {len(state.active_pois)} POIs in swing leg")
                               

                                liq_events = []
                                ob_events = []

                                for p in state.active_pois:
                                    if p.get('time') is None or not hasattr(p['time'], 'strftime'):
                                        continue

                                    ts_str = p['time'].strftime('%Y%m%d_%H%M')
                                    iso_time = p['time'].isoformat()

                                    if p['type'] == 'LIQ':
                                        liq_events.append({
                                            "id": f"4H_POI_LIQ_{ts_str}",
                                            "type": "POI-LIQ",
                                            "price": p['price_low'] if p['price_low'] is not None else p['price_high'],
                                            "time": iso_time,
                                            "if_valid": True
                                        })

                                    elif p['type'] == 'OB':
                                        ob_events.append({
                                            "id": f"4H_POI_OB_{ts_str}",
                                            "type": "POI-OB",
                                            "time_start": iso_time,
                                            "time_end": (p['time'] + pd.Timedelta(hours=4)).isoformat(),
                                            "low": p['price_low'],
                                            "high": p['price_high'],
                                            "if_valid": True
                                        })

                                if liq_events and event_loop is not None:
                                    payload = {"symbol": "EURUSD", "timeframe": "4H", "events": liq_events}
                                    asyncio.run_coroutine_threadsafe(event_manager.broadcast(payload), event_loop)

                                if ob_events and event_loop is not None:
                                    payload = {"symbol": "EURUSD", "timeframe": "4H", "events": ob_events}
                                    asyncio.run_coroutine_threadsafe(event_manager.broadcast(payload), event_loop)
                                
                                mapped_pois = []

                                for poi in state.active_pois:
                                    start_time = poi["time"]
                                    end_time = start_time + pd.Timedelta(hours=4) - pd.Timedelta(minutes=1)

                                    mapped = {
                                        "type": poi["type"],
                                        "trend": poi["trend"],
                                        "start_time": start_time,
                                        "end_time": end_time,
                                        "if_valid": True
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

                                state.mapped_pois = mapped_pois
                                buffer_5m_poi.clear()

                        if state.pullback_confirmed:
                            if state.swing_low and candle_4h["close"] < state.swing_low:
                                print(f"\n🟥 [4H CHOCH] BEARISH @ {candle_4h['time']}")
                                print(f"   | Previous Swing Low Broken: {state.swing_low}")
                                print(f"   | New Trend: BEARISH")
                                state.bos_time_4h = candle_4h["time"]
                                state.choch_level_4h = candle_4h["close"]
                                state.h4_structure_event = "CHOCH"
                                reset_on_4h_structure(state)
                                state.swing_high = max(c["high"] for c in leg_buffer_4h)
                                state.candidate_high = None
                                state.swing_low = None
                                state.candidate_low = candle_4h["low"]
                                state.trend_4h = "BEARISH"
                                state.pullback_confirmed = False
                                state.pullback_time = None
                                state.bullish_count = 0
                                state.bearish_count = 0
                                print(f"   | Structural Swing High (old leg): {state.swing_high}")
                                print(f"   | Initial Candidate Low: {state.candidate_low}")

                                # 📡 Broadcast CHOCH
                                event_payload = {
                                    "symbol": "EURUSD",
                                    "timeframe": "4h",
                                    "events": [
                                        {
                                            "id": f"4H_CHOCH_{candle_4h['time'].strftime('%Y%m%d_%H%M')}",
                                            "type": "CHOCH",
                                            "broken_level": state.choch_level_4h,
                                            "time": candle_4h["time"].isoformat()
                                        }
                                    ]
                                }
                                print(f"📡 Sending 4H CHOCH Event: {event_payload}")
                                if event_loop is not None:
                                    asyncio.run_coroutine_threadsafe(
                                        event_manager.broadcast(event_payload),
                                        event_loop
                                    )

                                buffer_5m.clear()  
                                leg_buffer_4h.clear()

                        if state.pullback_confirmed:
                            if state.trend_4h == "BULLISH" and state.swing_high is not None and candle_4h["close"] > state.swing_high:
                                print(f"\n🟦 [4H BOS] BULLISH @ {candle_4h['time']}")
                                print(f"   | Previous Swing High Broken: {state.swing_high}")
                                state.bos_level_4h = candle_4h["close"]
                                state.bos_time_4h= candle_4h["time"]
                                state.h4_structure_event="BOS"
                                reset_on_4h_structure(state)                
                                # 🔹 Calculate new swing LOW from old leg
                                if leg_buffer_4h:
                                    state.swing_low= min(c["low"] for c in leg_buffer_4h)
                                    print(f"   | New Swing Low (old leg): {state.swing_low}")
                                state.pullback_confirmed = False
                                state.pullback_time = None
                                state.bullish_count = 0
                                state.bearish_count = 0

                                # 📡 Broadcast BOS
                                event_payload = {
                                    "symbol": "EURUSD",
                                    "timeframe": "4h",
                                    "events": [
                                        {
                                            "id": f"4H_BOS_{candle_4h['time'].strftime('%Y%m%d_%H%M')}",
                                            "type": "BOS",
                                            "broken_level": state.bos_level_4h,
                                            "time": candle_4h["time"].isoformat()
                                        }
                                    ]
                                }
                                print(f"📡 Sending 4H BOS Event: {event_payload}")
                                if event_loop is not None:
                                    asyncio.run_coroutine_threadsafe(
                                        event_manager.broadcast(event_payload),
                                        event_loop
                                    )
                                    
                                leg_buffer_4h.clear()
                                buffer_5m.clear()

                    elif state.trend_4h == "BEARISH":
                        if state.candidate_low is None or candle_4h["low"] < state.candidate_low:
                            old_l = state.candidate_low
                            state.candidate_low = candle_4h["low"]
                            state.bullish_count = 0

                        if candle_4h["close"] > candle_4h["open"] and candle_4h["low"] > state.candidate_low:
                            state.bullish_count += 1

                        if state.swing_high and state.candidate_low:
                            depth_ratio = (candle_4h["high"] - state.candidate_low) / max(state.swing_high - state.candidate_low, 1e-9)
                            if state.pullback_confirmed==False and (state.bullish_count >= state.min_pullback_candles or depth_ratio >= state.pullback_pct):
                                state.pullback_confirmed = True
                                choch_5m=False
                                state.pullback_time = candle_4h["time"]
                                print(f"\n🌊 [4H BEARISH PB] CONFIRMED @ {state.pullback_time}")
                                print(f"   | Reason: {'Count (' + str(state.bullish_count) + ')' if state.bullish_count >= state.min_pullback_candles else 'Depth (' + f'{depth_ratio:.2f}' + ')'}")
                                state.h4_structure_event=None
                                state.swing_low = state.candidate_low
                                state.bullish_count = 0

                                if state.pullback_confirmed and state.pullback_time and state.swing_low:
                                    event_payload = {
                                        "symbol": "EURUSD",
                                        "timeframe": "4h",
                                        "events": [
                                            {
                                                "id": f"4H_PB_{state.pullback_time.strftime('%Y%m%d_%H%M')}",
                                                "type": "PULLBACK_CONFIRMED",
                                                "broken_level": state.swing_low,
                                                "time": state.pullback_time.isoformat()
                                            }
                                        ]
                                    }

                                    # Debug print
                                    print(f"📡 Sending 4H Pullback Event: {event_payload}")

                                    if event_loop is not None:
                                        asyncio.run_coroutine_threadsafe(
                                            event_manager.broadcast(event_payload),
                                            event_loop
                                        )

                                swing_df = pd.DataFrame(leg_buffer_4h).set_index("time")
                                # ---------------------------------------------------------
                                # 1️⃣ Detect POIs from BEARISH 4H swing
                                # ---------------------------------------------------------
                                state.active_pois = detect_pois_from_swing(
                                    ohlc_df=swing_df,
                                    trend="BEARISH"   # explicit bearish context
                                )

                                print(f"🔍 DETECTED {len(state.active_pois)} POIs in BEARISH 4H swing leg")

                                # ---------------------------------------------------------
                                # 2️⃣ Broadcast POIs to frontend (NO dedup, POIs already sorted)
                                # ---------------------------------------------------------
                                liq_events = []
                                ob_events = []

                                for p in state.active_pois:
                                    if p.get("time") is None or not hasattr(p["time"], "strftime"):
                                        continue

                                    ts_str = p["time"].strftime("%Y%m%d_%H%M")
                                    iso_time = p["time"].isoformat()

                                    # 🔻 BEARISH LIQ → usually buyside liquidity above highs
                                    if p["type"] == "LIQ":
                                        liq_events.append({
                                            "id": f"4H_POI_LIQ_{ts_str}",
                                            "type": "POI-LIQ",
                                            "price": p["price_high"] if p["price_high"] is not None else p["price_low"],
                                            "time": iso_time,
                                            "trend": "BEARISH",
                                            "if_valid": True
                                        })

                                    # 🔻 BEARISH OB → supply zone
                                    elif p["type"] == "OB":
                                        ob_events.append({
                                            "id": f"4H_POI_OB_{ts_str}",
                                            "type": "POI-OB",
                                            "time_start": iso_time,
                                            "time_end": (p["time"] + pd.Timedelta(hours=4)).isoformat(),
                                            "low": p["price_low"],
                                            "high": p["price_high"],
                                            "trend": "BEARISH",
                                            "if_valid": True
                                        })

                                # 📡 Send to frontend
                                if liq_events and event_loop is not None:
                                    payload = {
                                        "symbol": "EURUSD",
                                        "timeframe": "4H",
                                        "events": liq_events
                                    }
                                    asyncio.run_coroutine_threadsafe(
                                        event_manager.broadcast(payload),
                                        event_loop
                                    )

                                if ob_events and event_loop is not None:
                                    payload = {
                                        "symbol": "EURUSD",
                                        "timeframe": "4H",
                                        "events": ob_events
                                    }
                                    asyncio.run_coroutine_threadsafe(
                                        event_manager.broadcast(payload),
                                        event_loop
                                    )

                                # ---------------------------------------------------------
                                # 3️⃣ Convert 4H POIs → MINUTE TIMEFRAME (execution-ready)
                                # ---------------------------------------------------------
                                mapped_pois = []

                                for poi in state.active_pois:
                                    start_time = poi["time"]
                                    end_time = start_time + pd.Timedelta(hours=4) - pd.Timedelta(minutes=1)

                                    mapped = {
                                        "type": poi["type"],
                                        "trend": "BEARISH",
                                        "source_tf": "4H",
                                        "start_time": start_time,
                                        "end_time": end_time,
                                        "if_valid": True
                                    }

                                    # 🔻 Supply OB mapping
                                    if poi["type"] == "OB":
                                        mapped.update({
                                            "price_low": poi["price_low"],
                                            "price_high": poi["price_high"]
                                        })

                                    # 🔻 Liquidity mapping
                                    elif poi["type"] == "LIQ":
                                        mapped.update({
                                            "price": poi["price_high"] if poi["price_high"] is not None else poi["price_low"]
                                        })

                                    mapped_pois.append(mapped)

                                state.mapped_pois = mapped_pois
                                buffer_5m_poi.clear()

                        if state.pullback_confirmed:
                            if state.swing_high and candle_4h["close"] > state.swing_high:
                                print(f"\n🟩 [4H CHOCH] BULLISH @ {candle_4h['time']}")
                                print(f"   | Previous Swing High Broken: {state.swing_high}")
                                print(f"   | New Trend: BULLISH")
                                state.bos_time_4h = candle_4h["time"]
                                state.choch_level_4h = candle_4h["close"]
                                state.h4_structure_event="CHOCH"
                                reset_on_4h_structure(state)
                                state.swing_low = min(c["low"] for c in leg_buffer_4h)
                                state.candidate_high = candle_4h["high"]
                                state.trend_4h = "BULLISH"
                                state.pullback_confirmed = False
                                state.pullback_time = None
                                state.bullish_count = 0
                                state.bearish_count = 0
                                print(f"   | Structural Swing Low (old leg): {state.swing_low}")
                                print(f"   | Initial Candidate High: {state.candidate_high}")

                                # 📡 Broadcast CHOCH
                                event_payload = {
                                    "symbol": "EURUSD",
                                    "timeframe": "4h",
                                    "events": [
                                        {
                                            "id": f"4H_CHOCH_{candle_4h['time'].strftime('%Y%m%d_%H%M')}",
                                            "type": "CHOCH",
                                            "broken_level": state.choch_level_4h,
                                            "time": candle_4h["time"].isoformat()
                                        }
                                    ]
                                }
                                print(f"📡 Sending 4H CHOCH Event: {event_payload}")
                                if event_loop is not None:
                                    asyncio.run_coroutine_threadsafe(
                                        event_manager.broadcast(event_payload),
                                        event_loop
                                    )

                                buffer_5m.clear()  
                                leg_buffer_4h.clear()

                        if state.pullback_confirmed:
                            if state.trend_4h == "BEARISH" and state.swing_low is not None and candle_4h["close"] < state.swing_low:
                                print(f"\n🟦 [4H BOS] BEARISH @ {candle_4h['time']}")
                                print(f"   | Previous Swing Low Broken: {state.swing_low}")
                                state.bos_level_4h = candle_4h["close"]
                                state.bos_time_4h = candle_4h["time"]
                                state.h4_structure_event="BOS"
                                reset_on_4h_structure(state)
                                # 🔹 New swing HIGH from previous leg
                                if leg_buffer_4h:
                                    state.swing_high = max(c["high"] for c in leg_buffer_4h)
                                    print(f"   | New Swing High (old leg): {state.swing_high}")
                                state.pullback_confirmed = False
                                state.pullback_time = None
                                state.bullish_count = 0
                                state.bearish_count = 0

                                # 📡 Broadcast BOS
                                event_payload = {
                                    "symbol": "EURUSD",
                                    "timeframe": "4h",
                                    "events": [
                                        {
                                            "id": f"4H_BOS_{candle_4h['time'].strftime('%Y%m%d_%H%M')}",
                                            "type": "BOS",
                                            "broken_level": state.bos_level_4h,
                                            "time": candle_4h["time"].isoformat()
                                        }
                                    ]
                                }
                                print(f"📡 Sending 4H BOS Event: {event_payload}")
                                if event_loop is not None:
                                    asyncio.run_coroutine_threadsafe(
                                        event_manager.broadcast(event_payload),
                                        event_loop
                                    )
                                    
                                leg_buffer_4h.clear()
                                buffer_5m.clear()

                # --------------------------------------------------
                # 5M GATING LOGIC
                # --------------------------------------------------

                # ❌ Gate 1: Ignore all 5M candles until 4H pullback is confirmed
                if not state.pullback_confirmed or not state.mapped_pois or len(state.mapped_pois) == 0:
                    continue

                bull_candle_5m = candle_5m["close"] > candle_5m["open"]
                bear_candle_5m = candle_5m["close"] < candle_5m["open"]
                if state.trend_4h=="BULLISH":
                    if state.candidate_low_5m is None:
                        state.market_trend_5m="BEARISH"
                        state.candidate_low_5m = candle_5m["low"]
                        state.pullback_count_5m = 0
                        if state.swing_high_5m is None:
                            state.swing_high_5m = candle_5m["high"]
                            state.swing_high_5m_time = candle_5m["time"]
                        continue

                    if state.market_trend_5m=="BEARISH":
                        if bull_candle_5m and (state.pullback_count_5m == 0 or state.pullback_count_5m == 1):
                            state.pullback_count_5m += 1

                        if candle_5m["low"] < state.candidate_low_5m and state.pullback_count_5m<2:
                            state.candidate_low_5m = candle_5m["low"]
                            state.pullback_count_5m = 0

                        retrace = (candle_5m["high"] - state.candidate_low_5m) / max(state.swing_high_5m - state.candidate_low_5m, 1e-9)
                        valid_pullback_5m = state.pullback_count_5m >= 2 or retrace >= 0.75

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
                                if candle_5m["high"] > state.swing_high_5m :
                                    state.swing_low_5m = state.candidate_low_5m
                                    state.market_trend_5m="BULLISH"
                                    state.pullback_count_5m=0
                                    state.candidate_high_5m= candle_5m["high"]
                                    print(f"🚀 5M BULLISH CHOCH @ {candle_5m['time']} | Broken High: {state.swing_high_5m}")
                                    state.buffer_5m_sh.clear()
                    if state.market_trend_5m=="BULLISH":
                        if bear_candle_5m and (state.pullback_count_5m == 0 or state.pullback_count_5m == 1):
                            state.pullback_count_5m += 1

                        if candle_5m["high"] > state.candidate_high_5m and state.pullback_count_5m<2:
                            state.candidate_high_5m = candle_5m["high"]
                            state.pullback_count_5m = 0

                        retrace=(state.candidate_high_5m - candle_5m["low"]) / max(
                                        state.candidate_high_5m - state.swing_low_5m, 1e-9
                                    )
                        valid_pullback_5m = state.pullback_count_5m >= 2 or retrace >= 0.99
                        print(f"   5M Pullback Check: Count={state.pullback_count_5m}, Retrace={retrace:.2f}, Valid={valid_pullback_5m}")

                        if valid_pullback_5m:
                            state.buffer_5m_sl.append(candle_5m)    
                            #BOS 5m                        
                            if candle_5m["high"] < state.candidate_high_5m:
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

                                #CHOCH 5m
                                if candle_5m["low"] > state.swing_low_5m :
                                    state.swing_high_5m = state.candidate_high_5m
                                    state.market_trend_5m="BEARISH"
                                    state.pullback_count_5m=0
                                    state.candidate_low_5m= candle_5m["low"]
                                    print(f"🚀 5M BEARISH CHOCH @ {candle_5m['time']} | Broken Low: {state.swing_low_5m}")
                                    state.buffer_5m_sl.clear()
                    # --------------------------------------------------
                    # 5M POI TAP CHECK (Realtime)
                    # --------------------------------------------------
                    if state.mapped_pois and not state.poi_tapped and state.active_poi is None:

                        for poi in state.mapped_pois:
                            if not poi["if_valid"]:
                                continue

                            if poi["type"] == "OB":
                                if candle_5m["low"] <= poi["price_high"] and candle_5m["high"] >= poi["price_low"]:
                                    state.poi_tapped = True
                                    state.active_poi = poi
                                    state.poi_tapped_level = candle_5m["low"]
                                    state.poi_tapped_time = candle_5m["time"]
                                    print(f"🎯 POI TAPPED (OB) @ {candle_5m['time']}")
                                    poi["if_valid"]=False
                                    break

                            elif poi["type"] == "LIQ":
                                if candle_5m["low"] <= poi["price"]:
                                    state.poi_tapped = True
                                    state.active_poi = poi
                                    state.poi_tapped_level = candle_5m["low"]
                                    state.poi_tapped_time = candle_5m["time"]
                                    print(f"🎯 POI TAPPED (LIQ) @ {candle_5m['time']}")
                                    poi["if_valid"]=False
                                    break


                        if state.poi_tapped:
                            active_poi = state.active_poi


                            next_poi = None
                            for poi in state.mapped_pois:
                                    if not poi["if_valid"]:
                                        continue
                                    else:
                                        next_poi = poi
                                        break  

                            p0_type = active_poi["type"]

                            
                            if next_poi:
                                p1_type = next_poi["type"]

                                if p0_type == "OB" and p1_type == "OB":
                                    invalidation_level = (active_poi["price_high"] + next_poi["price_high"]) / 2

                                elif p0_type == "OB" and p1_type == "LIQ":
                                    invalidation_level = (active_poi["price_high"] + next_poi["price"]) / 2

                                elif p0_type == "LIQ" and p1_type == "LIQ":
                                    invalidation_level = (active_poi["price"] + next_poi["price"]) / 2
                                elif p0_type=="LIQ" and p1_type=="OB":
                                    invalidation_level = (active_poi["price"] + next_poi["price_high"]) / 2
                                    

                            else:
                                # No next POI → fallback to 4H swing low
                                if p0_type == "OB":
                                    invalidation_level = (active_poi["price_high"] + state.swing_low) / 2
                                else:
                                    invalidation_level = (active_poi["price"] + state.swing_low) / 2
                        

                    if not state.choch_5m and state.active_poi :
                        if candle_5m["low"]<= invalidation_level:
                            state.active_poi=None
                            state.poi_tapped=False
                            continue
                        if candle_5m["high"] > state.swing_high_5m :
                            state.choch_5m=True
                            state.trade_active 
                            state.active_poi=None
                            state.poi_tapped=False
                            # 📡 Broadcast 5M CHOCH
                            event_payload = {
                                "symbol": "EURUSD",
                                "timeframe": "5m",
                                "events": [
                                    {
                                        "id": f"5m_CHOCH_{candle_5m['time'].strftime('%Y%m%d_%H%M')}",
                                        "type": "CHOCH",
                                        "broken_level": state.swing_high_5m,
                                        "time": candle_5m["time"].isoformat()
                                    }
                                ]
                            }
                            print(f"📡 Sending 5M CHOCH (BULLISH): {event_payload}")
                            if event_loop is not None:
                                asyncio.run_coroutine_threadsafe(event_manager.broadcast(event_payload), event_loop)
                        # --------------------------------------------------
                        # TRADE SETUP (CHOCH + POI)
                        # --------------------------------------------------
                        if (
                            state.choch_5m
                        ):
                            state.choch_5m=False            
                            # ==================================================
                            # DETERMINE RANGE FOR 50% CALCULATION
                            # ==================================================
                            if state.trend_4h == "BULLISH":
                                # 4H bullish → 5M CHOCH is bullish break
                                range_high = state.swing_high_5m          # CHOCH candle high
                                range_low = state.swing_low_5m            # last bearish swing low
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

                            # 📡 Broadcast 5M Retracement & Trade Plan
                            ts_str = candle_5m['time'].strftime('%Y%m%d_%H%M')
                            iso_start = candle_5m['time'].isoformat()
                            iso_end = (candle_5m['time'] + pd.Timedelta(minutes=25)).isoformat()
                            
                            # Retracement payload
                            retr_event = {
                                "symbol": SYMBOL,
                                "timeframe": "5m",
                                "events": [
                                    {
                                        "id": f"5m_RETR_{ts_str}",
                                        "type": "RETRACEMENT",
                                        "start": float(range_low),
                                        "end": float(range_high),
                                        "mid": float(entry),
                                        "time_start": iso_start,
                                        "time_end": iso_end,
                                        "extend_candles": 5
                                    }
                                ]
                            }
                            
                            # Trade Plan payload
                            plan_event = {
                                "symbol": SYMBOL,
                                "timeframe": "5m",
                                "events": [
                                    {
                                        "id": f"5m_RETR_{ts_str}",
                                        "type": "TRADE_PLAN",
                                        "plan_direction": "LONG" if direction == "BUY" else "SHORT",
                                        "SL": float(stop_loss),
                                        "TP": float(take_profit),
                                        "Entry": float(entry),
                                        "time_start": iso_start,
                                        "time_end": iso_end
                                    }
                                ]
                            }
                            
                            print(f"📡 Sending 5M Retracement & Trade Plan: {ts_str}")
                            if event_loop is not None:
                                asyncio.run_coroutine_threadsafe(event_manager.broadcast(retr_event), event_loop)
                                asyncio.run_coroutine_threadsafe(event_manager.broadcast(plan_event), event_loop)

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


                if state.trend_4h == "BEARISH":
                    # MIRRORED VERSION OF BULLISH LOGIC
                    if state.candidate_high_5m is None:
                        state.market_trend_5m = "BULLISH"
                        state.candidate_high_5m = candle_5m["high"]
                        state.pullback_count_5m = 0
                        if state.swing_low_5m is None:
                            state.swing_low_5m = candle_5m["low"]
                            state.swing_low_5m_time = candle_5m["time"]
                        continue

                    if state.market_trend_5m == "BULLISH":
                        if bear_candle_5m and (state.pullback_count_5m == 0 or state.pullback_count_5m == 1):
                            state.pullback_count_5m += 1

                        if candle_5m["high"] > state.candidate_high_5m and state.pullback_count_5m < 2:
                            state.candidate_high_5m = candle_5m["high"]
                            state.pullback_count_5m = 0

                        retrace = (state.candidate_high_5m - candle_5m["low"]) / max(state.candidate_high_5m - state.swing_low_5m, 1e-9)
                        valid_pullback_5m = state.pullback_count_5m >= 2 or retrace >= 0.75

                        if valid_pullback_5m:
                            state.buffer_5m_sl.append(candle_5m)
                            # BOS 5m (BEARISH VERSION)
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

                                # CHOCH 5m (BEARISH VERSION)
                                if candle_5m["low"] < state.swing_low_5m:
                                    state.swing_high_5m = state.candidate_high_5m
                                    state.market_trend_5m = "BEARISH"
                                    state.pullback_count_5m = 0
                                    state.candidate_low_5m = candle_5m["low"]
                                    print(f"🚀 5M BEARISH CHOCH @ {candle_5m['time']} | Broken Low: {state.swing_low_5m}")
                                    state.buffer_5m_sl.clear()

                    if state.market_trend_5m == "BEARISH":
                        if bull_candle_5m and (state.pullback_count_5m == 0 or state.pullback_count_5m == 1):
                            state.pullback_count_5m += 1

                        if candle_5m["low"] < state.candidate_low_5m and state.pullback_count_5m < 2:
                            state.candidate_low_5m = candle_5m["low"]
                            state.pullback_count_5m = 0

                        retrace = (candle_5m["high"] - state.candidate_low_5m) / max(state.swing_high_5m - state.candidate_low_5m, 1e-9)
                        valid_pullback_5m = state.pullback_count_5m >= 2 or retrace >= 0.99
                        print(f"   5M Pullback Check: Count={state.pullback_count_5m}, Retrace={retrace:.2f}, Valid={valid_pullback_5m}")

                        if valid_pullback_5m:
                            state.buffer_5m_sh.append(candle_5m)
                            # BOS 5m (BEARISH VERSION)
                            if candle_5m["low"] < state.candidate_low_5m:
                                swing_candle = max(
                                    state.buffer_5m_sh,
                                    key=lambda c: c["high"]
                                )

                                state.swing_high_5m = swing_candle["high"]
                                state.swing_high_5m_time = swing_candle["time"]
                                state.protected_5m_point = state.swing_high_5m
                                state.protected_5m_time = state.swing_high_5m_time

                                state.candidate_low_5m = candle_5m["low"]
                                state.pullback_count_5m = 0
                                state.buffer_5m_sh.clear()

                                # CHOCH 5m (BEARISH VERSION)
                                if candle_5m["high"] > state.swing_high_5m:
                                    state.swing_low_5m = state.candidate_low_5m
                                    state.market_trend_5m = "BULLISH"
                                    state.pullback_count_5m = 0
                                    state.candidate_high_5m = candle_5m["high"]
                                    print(f"🚀 5M BULLISH CHOCH @ {candle_5m['time']} | Broken High: {state.swing_high_5m}")
                                    state.buffer_5m_sh.clear()

                    # --------------------------------------------------
                    # 5M POI TAP CHECK (MIRRORED FOR BEARISH)
                    # --------------------------------------------------
                    if state.mapped_pois and not state.poi_tapped and state.active_poi is None:
                        for poi in state.mapped_pois:
                            if not poi["if_valid"]:
                                continue

                            if poi["type"] == "OB":
                                # MIRRORED: For BEARISH trend, check if price touches OB from above
                                if candle_5m["high"] >= poi["price_low"] and candle_5m["low"] <= poi["price_high"]:
                                    state.poi_tapped = True
                                    state.active_poi = poi
                                    state.poi_tapped_level = candle_5m["high"]  # MIRRORED: Use high instead of low
                                    state.poi_tapped_time = candle_5m["time"]
                                    print(f"🎯 POI TAPPED (OB) @ {candle_5m['time']}")
                                    poi["if_valid"] = False
                                    break

                            elif poi["type"] == "LIQ":
                                # MIRRORED: For BEARISH trend, check if price sweeps LIQ from above
                                if candle_5m["high"] >= poi["price"]:
                                    state.poi_tapped = True
                                    state.active_poi = poi
                                    state.poi_tapped_level = candle_5m["high"]  # MIRRORED: Use high instead of low
                                    state.poi_tapped_time = candle_5m["time"]
                                    print(f"🎯 POI TAPPED (LIQ) @ {candle_5m['time']}")
                                    poi["if_valid"] = False
                                    break

                        if state.poi_tapped:
                            active_poi = state.active_poi

                            next_poi = None
                            for poi in state.mapped_pois:
                                if not poi["if_valid"]:
                                    continue
                                else:
                                    next_poi = poi
                                    break

                            p0_type = active_poi["type"]

                            if next_poi:
                                p1_type = next_poi["type"]

                                # MIRRORED: For BEARISH, check lows instead of highs
                                if p0_type == "OB" and p1_type == "OB":
                                    invalidation_level = (active_poi["price_low"] + next_poi["price_low"]) / 2

                                elif p0_type == "OB" and p1_type == "LIQ":
                                    invalidation_level = (active_poi["price_low"] + next_poi["price"]) / 2

                                elif p0_type == "LIQ" and p1_type == "LIQ":
                                    invalidation_level = (active_poi["price"] + next_poi["price"]) / 2
                                elif p0_type == "LIQ" and p1_type == "OB":
                                    invalidation_level = (active_poi["price"] + next_poi["price_low"]) / 2

                            else:
                                # MIRRORED: Fallback to 4H swing high for BEARISH
                                if p0_type == "OB":
                                    invalidation_level = (active_poi["price_low"] + state.swing_high) / 2
                                else:
                                    invalidation_level = (active_poi["price"] + state.swing_high) / 2

                    if not state.choch_5m and state.active_poi:
                        # MIRRORED: Check if price goes above invalidation level
                        if candle_5m["high"] >= invalidation_level:
                            state.active_poi = None
                            state.poi_tapped = False
                            continue
                        
                        # MIRRORED: For BEARISH, check BEARISH CHOCH (price breaks below swing_low)
                        if candle_5m["low"] < state.swing_low_5m:
                            state.choch_5m = True
                            state.trade_active = True
                            state.active_poi = None
                            state.poi_tapped = False
                            
                            # 📡 Broadcast 5M CHOCH (BEARISH VERSION)
                            event_payload = {
                                "symbol": "EURUSD",
                                "timeframe": "5m",
                                "events": [
                                    {
                                        "id": f"5m_CHOCH_{candle_5m['time'].strftime('%Y%m%d_%H%M')}",
                                        "type": "CHOCH",
                                        "broken_level": state.swing_low_5m,  # MIRRORED: Use low instead of high
                                        "direction": "BEARISH",
                                        "time": candle_5m["time"].isoformat()
                                    }
                                ]
                            }
                            print(f"📡 Sending 5M CHOCH (BEARISH): {event_payload}")
                            if event_loop is not None:
                                asyncio.run_coroutine_threadsafe(event_manager.broadcast(event_payload), event_loop)

                        # --------------------------------------------------
                        # TRADE SETUP (CHOCH + POI) - MIRRORED FOR BEARISH
                        # --------------------------------------------------
                        if state.choch_5m:
                            state.choch_5m = False
            
                            # ==================================================
                            # DETERMINE RANGE FOR 50% CALCULATION - MIRRORED
                            # ==================================================
                            if state.trend_4h == "BEARISH":  # CHANGED TO BEARISH
                                # 4H bearish → 5M CHOCH is bearish break
                                range_high = state.swing_high_5m  # Last bullish swing high
                                range_low = state.swing_low_5m    # CHOCH candle low
                                direction = "SELL"  # MIRRORED: SELL instead of BUY

                            # Safety check
                            if range_high is None or range_low is None:
                                print("❌ Invalid range — trade skipped")
                                continue

                            # ==================================================
                            # 50% RETRACEMENT ENTRY - MIRRORED FOR SELL
                            # ==================================================
                            entry = (range_high + range_low) / 2

                            pip = 0.0001

                            if direction == "SELL":  # MIRRORED
                                stop_loss = range_high + 4 * pip  # MIRRORED: Above range
                                risk = stop_loss - entry  # MIRRORED: Risk calculation
                                take_profit = entry - 3 * risk  # MIRRORED: Downwards target

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

                            # 📡 Broadcast 5M Retracement & Trade Plan
                            ts_str = candle_5m['time'].strftime('%Y%m%d_%H%M')
                            iso_start = candle_5m['time'].isoformat()
                            iso_end = (candle_5m['time'] + pd.Timedelta(minutes=25)).isoformat()
                            
                            # Retracement payload
                            retr_event = {
                                "symbol": SYMBOL,
                                "timeframe": "5m",
                                "events": [
                                    {
                                        "id": f"5m_RETR_{ts_str}",
                                        "type": "RETRACEMENT",
                                        "start": float(range_low),
                                        "end": float(range_high),
                                        "mid": float(entry),
                                        "time_start": iso_start,
                                        "time_end": iso_end,
                                        "extend_candles": 5
                                    }
                                ]
                            }
                            
                            # Trade Plan payload - MIRRORED FOR SELL
                            plan_event = {
                                "symbol": SYMBOL,
                                "timeframe": "5m",
                                "events": [
                                    {
                                        "id": f"5m_RETR_{ts_str}",
                                        "type": "TRADE_PLAN",
                                        "plan_direction": "SHORT",  # MIRRORED: SHORT instead of LONG
                                        "SL": float(stop_loss),
                                        "TP": float(take_profit),
                                        "Entry": float(entry),
                                        "time_start": iso_start,
                                        "time_end": iso_end
                                    }
                                ]
                            }
                            
                            print(f"📡 Sending 5M Retracement & Trade Plan: {ts_str}")
                            if event_loop is not None:
                                asyncio.run_coroutine_threadsafe(event_manager.broadcast(retr_event), event_loop)
                                asyncio.run_coroutine_threadsafe(event_manager.broadcast(plan_event), event_loop)

                            print("🚀 TRADE PLANNED & STORED")
                            print(f"   Direction : {direction}")
                            print(f"   Entry     : {entry}")
                            print(f"   SL        : {stop_loss}")
                            print(f"   TP        : {take_profit}")

                    # --------------------------------------------------
                    # TRADE MANAGEMENT (SELL ONLY - Realtime 5M) - MIRRORED
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
                                    tp_2pct_level = entry - 0.02 * (entry - tp)  # MIRRORED: Downwards

                                    if candle_low <= tp_2pct_level:
                                        print(f"🟥 TP MOVE WITHOUT ENTRY (2% HIT @ {tp_2pct_level}) → TRADE INVALID")

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
                                # STOP LOSS (SELL VERSION)
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
                                # TAKE PROFIT (SELL VERSION)
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