from datetime import datetime , timezone
from pathlib import Path
import csv
import pandas as pd
import time
import threading
from typing import Dict, Optional

import asyncio
from ws.manager import ws_manager
from ws.event_manager import event_manager
from db.supabase_client import supabase

from backend.engine1.registry import StateRegistry
from backend.engine.poi_detection import detect_pois_from_swing 

MAX_REPLAY = 1000 
SIMULATE_REALTIME = True
PAUSE_ON_EACH_EVENT = False
PAUSE_ON_DATES: list[str] = []
PAUSE_SECONDS = 0.05
registry = StateRegistry()

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
# TRADING ENGINE CLASS
# ==================================================
class TradingEngine:

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.state = registry.get_state(symbol) 
        self.running = False
        self.thread = None
        
        # Buffers
        self.bucket_5m = []
        self.buffer_5m = []   
        self.buffer_5m_poi = []   
        self.state.leg_buffer_4h = []     

        # If trend is NEUTRAL or bos_time is missing, we need to bootstrap it.
        if self.state.trend_4h == "NEUTRAL" or self.state.bos_time_4h is None:
            print(f"*** [BOOTSTRAP] Initializing state for {self.symbol}...")
            #print()
            self.state.pullback_pct = 0.35
            self.state.min_pullback_candles = 10
            
            if self.symbol == "EURUSD":
                self.state.trend_4h = "BEARISH"
                self.state.swing_low = None       
                self.state.swing_high = 1.14827         
                self.state.bos_time_4h = datetime(2022, 1, 25, 4, 0)
            elif self.symbol == "GBPJPY":
                self.state.trend_4h = "BEARISH"
                self.state.swing_low = None
                self.state.swing_high = 157.766
                self.state.bos_time_4h = datetime(2022, 1, 20, 16, 0)
            elif self.symbol == "EURAUD":
                self.state.trend_4h = "BULLISH"
                self.state.swing_low = 1.55735
                self.state.swing_high = None
                self.state.bos_time_4h = datetime(2022, 1, 17, 0, 0)
            elif self.symbol == "GBPCHF":
                self.state.trend_4h = "BEARISH"
                self.state.swing_low = None
                self.state.swing_high = 1.26087
                self.state.bos_time_4h = datetime(2022, 1, 24, 0, 0)
            elif self.symbol == "USDCAD":
                self.state.trend_4h = "BEARISH"
                self.state.swing_low = None
                self.state.swing_high = 1.28134
                self.state.bos_time_4h = datetime(2022, 1, 19, 8, 0)
            else:
                # Fallback / Placeholder for others
                self.state.trend_4h = "BEARISH"
                self.state.bos_time_4h = datetime(2022, 1, 20, 0, 0)

            self.state.candidate_high = None
            self.state.candidate_high_time = None
            self.state.candidate_low = None
            self.state.candidate_low_time = None
            self.state.candidate_high_5m = None
            self.state.candidate_high_5m_time = None
            self.state.candidate_low_5m = None
            self.state.candidate_low_5m_time = None
            self.state.pullback_confirmed_5m = False
            self.state.pullback_confirmed = False
            self.state.pullback_time = None
            self.state.bearish_count = 0
            self.state.bullish_count = 0
            self.state.red_count = 0
            self.state.green_count = 0
            self.state.bos_count_5m = 0
        
        self.state.trigger_choch_poi = False
        self.state.choch_broken_level = None
        self.state.choch_broken_time = None

    def send_event(self, payload: dict):
        """Thread-safe pass-through to `event_manager.send_threadsafe` (no simulation pauses)."""
        try:
            event_manager.send_threadsafe(payload)
        except Exception as e:
            print(f"[WARN] Failed to send event: {e}")

    def reset_on_4h_structure(self):
        self.state.mapped_pois = []
        self.state.active_poi = None
        self.state.poi_tapped = False
        self.state.poi_tapped_level = None
        self.state.poi_tapped_time = None

        self.state.trend_5m = None

        # self.state.swing_high_5m = None
        # self.state.swing_low_5m = None
        # self.state.swing_high_5m_time = None
        # self.state.swing_low_5m_time = None
        self.state.candidate_high_5m = None
        self.state.candidate_high_5m_time = None
        self.state.candidate_low_5m = None
        self.state.candidate_low_5m_time = None
        self.state.pullback_count_5m = 0
        self.state.market_trend_5m = None
        self.state.choch_5m = False
        self.state.pullback_confirmed_5m = False
        self.state.bos_count_5m = 0
        self.state.no_invalidation = False

        self.state.buffer_5m_sh.clear()
        self.state.buffer_5m_sl.clear()

        self.state.active_pois = []

        self.state.trade = None
        self.state.trade_planned = False
        self.state.entry_filled = False
        
        print(f"[DEBUG] reset_on_4h_structure called. Reseting 5M structure from High: {self.state.swing_high_5m}, Low: {self.state.swing_low_5m}")
        self.state.entry_filled = False

    def save_trade_to_db(self, trade_date, side, result, entry, exit_price, pnl):
        data = {
            "pair": self.symbol,
            "trade_date": str(trade_date),
            "side": side,
            "result": result,
            "entry": float(entry),
            "exit_price": float(exit_price),
            "pnl": float(pnl),
        }

        try:
            supabase.table("backtest_trades").insert(data).execute()

        except Exception as e:
            print(f"[ERROR] DB Exception for {self.symbol}: {e}")

    def run(self):
        """Main execution loop for this pair."""
        print("=" * 60)
        print(f"Trading Agent - REALTIME MODE ({self.symbol})")
        print("=" * 60)
        time.sleep(10)
        

        base_dir = Path(__file__).resolve().parent.parent
        potential_paths = [
            base_dir / f"DAT_MT_{self.symbol}_M1_2022.csv",
            base_dir / f"HISTDATA_COM_MT_{self.symbol}_M12022/DAT_MT_{self.symbol}_M1_2022.csv"
        ]
        print(f"[{self.symbol}] Checking CSV paths: {[str(p) for p in potential_paths]}")
        #print()
        minute_csv_path = next((p for p in potential_paths if p.exists()), None)
        
        if not minute_csv_path:
            print(f"[ERROR] CSV not found for {self.symbol}. Checked: {[str(p) for p in potential_paths]}")
            return

        self.running = True
        
        try:
            with open(minute_csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)

                for row in reader:
                    if not self.running:
                        print(f"[STOP] Engine stopped for {self.symbol}")
                        return

                    if len(row) < 6:
                        continue

                    date_str, time_str, o, h, l, c = row[:6]
                    try:
                        t = datetime.strptime(date_str + " " + time_str, "%Y.%m.%d %H:%M")

                        # Pause on specific dates for debugging
                        if t.month == 12 and t.day == 25:
                            print("Reached dec 25 — sleeping for 1 hour to keep backend alive...")
                            time.sleep(3600)
                        # Smart Sleep: 
                        # - History: 2ms (Fast but stable for WebSockets)
                        # - Live: 50ms (Readable speed)
                        # if self.state.bos_time_4h and t > self.state.bos_time_4h:
                        #     time.sleep(0.0001) 
                        # else:
                        #     time.sleep(0.0001) 
                        
                        self.state.last_candle_time = t
                            
                        candle_1m = Candle(
                            time=t,
                            open_=float(o),
                            high=float(h),
                            low=float(l),
                            close=float(c)
                        )
                        floored_5m_time = candle_1m.time.replace(
                            minute=(candle_1m.time.minute // 5) * 5,
                            second=0,
                            microsecond=0
                        
                        )
                        new_5m_candle = False
                        if not self.bucket_5m:
                            self.bucket_5m.append(candle_1m)
                            self.curr_5m_time = floored_5m_time
                        elif floored_5m_time == self.curr_5m_time:
                            self.bucket_5m.append(candle_1m)
                        else:
                            candle_5m = {
                                "time": self.curr_5m_time,
                                "open": self.bucket_5m[0].open,
                                "high": max(c.high for c in self.bucket_5m),
                                "low": min(c.low for c in self.bucket_5m),
                                "close": self.bucket_5m[-1].close,
                            }

                            # ws_manager.send_threadsafe({
                            #     "type": "candle",
                            #     "symbol": self.symbol,
                            #     "tf": "5m",
                            #     "timestamp": int(self.curr_5m_time.timestamp() * 1000),
                            #     "open": candle_5m["open"],
                            #     "high": candle_5m["high"],
                            #     "low": candle_5m["low"],
                            #     "close": candle_5m["close"],
                            # })

                            # replay buffer disabled (frontend reads candles from CSV)

                            self.buffer_5m.append(candle_5m)
                            self.buffer_5m_poi.append(candle_5m)

                            # Reset bucket for next 5m window
                            self.bucket_5m.clear()
                            self.bucket_5m.append(candle_1m)
                            self.curr_5m_time = floored_5m_time
                            new_5m_candle = True
                            
                        # ---------------- 4H CANDLE ----------------
                        if new_5m_candle and self.buffer_5m:
                            last_5m_candle = self.buffer_5m[-1]
                            floored_4h_time = last_5m_candle["time"].replace(
                                hour=(last_5m_candle["time"].hour // 4) * 4,
                                minute=0,
                                second=0,
                                microsecond=0
                            )

                            # First 4h bucket
                            if not hasattr(self, "curr_4h_time"):
                                self.curr_4h_time = floored_4h_time
                                self.curr_4h_bucket = [last_5m_candle]

                            # Same 4h window → append
                            elif floored_4h_time == self.curr_4h_time:
                                self.curr_4h_bucket.append(last_5m_candle)

                            # New 4h window → finalize previous candle
                            else:
                                candle_4h = {
                                    "time": self.curr_4h_time,
                                    "open": self.curr_4h_bucket[0]["open"],
                                    "high": max(c["high"] for c in self.curr_4h_bucket),
                                    "low": min(c["low"] for c in self.curr_4h_bucket),
                                    "close": self.curr_4h_bucket[-1]["close"],
                                }

                                    # ws_manager.send_threadsafe({
                                    #     "type": "candle",
                                    #     "symbol": self.symbol,
                                    #     "tf": "4h",
                                    #     "timestamp": int(self.curr_4h_time.timestamp() * 1000),
                                    #     "open": candle_4h["open"],
                                    #     "high": candle_4h["high"],
                                    #     "low": candle_4h["low"],
                                    #     "close": candle_4h["close"],
                                    # })
                                                        
                                self.curr_4h_time = floored_4h_time
                                self.curr_4h_bucket = [last_5m_candle]
                                self.state.leg_buffer_4h.append(candle_4h)
                                self.buffer_5m.clear()

                                # --------------------------------------------------
                                # 3. 4H EVENT LOGIC (State Reconstruction)
                                # --------------------------------------------------
                                
                                
                                is_historical = self.state.bos_time_4h and candle_4h["time"] <= self.state.bos_time_4h
                                if not is_historical:
                                
                                    # -----------------------------
                                    # 3A. Update Pullback State
                                    # ----------------------------- 

                                    if self.state.trend_4h == "BULLISH":
                                        if self.state.candidate_high is None or candle_4h["high"] > self.state.candidate_high:
                                            self.state.candidate_high = candle_4h["high"]
                                            self.state.candidate_high_time = candle_4h["time"]
                                            self.state.bearish_count = 0
                                            self.state.green_count=0

                                        if candle_4h["close"] < candle_4h["open"] and candle_4h["high"] < self.state.candidate_high:
                                            self.state.bearish_count += 1
                                        if self.state.bearish_count > 0 and self.state.bearish_count <= 10 and candle_4h["close"] > candle_4h["open"]:
                                            self.state.green_count+=1


                                        if self.state.swing_low and self.state.candidate_high:
                                            depth_ratio = (self.state.candidate_high - min(candle_4h["low"], candle_4h["close"])) / max(self.state.candidate_high - self.state.swing_low, 1e-9)
                                            if self.state.pullback_confirmed==False and (self.state.bearish_count >= self.state.min_pullback_candles or ( depth_ratio >= self.state.pullback_pct and self.state.green_count>=6)):
                                                self.state.pullback_confirmed = True
                                                choch_5m=False
                                                self.state.pullback_time = candle_4h["time"]
                                                print(f"\n[PULLBACK] [4H BULLISH PB] CONFIRMED @ {self.state.pullback_time}")
                                                #print()
                                                self.state.h4_structure_event=None
                                                self.state.swing_high = self.state.candidate_high
                                                self.state.swing_high_time = self.state.candidate_high_time

                                                if self.state.pullback_confirmed and self.state.pullback_time and self.state.swing_high:
                                                    if not is_historical:
                                                        event_payload = {
                                                            "symbol": self.symbol,
                                                            "timeframe": "4h",
                                                            "events": [
                                                                {
                                                                    "id": f"4H_PB_{self.state.pullback_time.strftime('%Y%m%d_%H%M')}",
                                                                    "type": "PULLBACK_CONFIRMED",
                                                                    "broken_level": candle_4h["low"],
                                                                    "time": self.state.pullback_time.isoformat()
                                                                }
                                                            ]
                                                        }
                                                        self.send_event(event_payload)
                                                        # Also send to 5m timeframe for plotting
                                                        floored_5m_pb_time = self.state.pullback_time.replace(
                                                            minute=(self.state.pullback_time.minute // 5) * 5,
                                                            second=0,
                                                            microsecond=0
                                                        )

                                                        event_payload_5m = {
                                                            "symbol": self.symbol,
                                                            "timeframe": "5m",
                                                            "events": [
                                                                {
                                                                    "id": f"5m_4H_PB_{floored_5m_pb_time.strftime('%Y%m%d_%H%M')}",
                                                                    "type": "PULLBACK_CONFIRMED",
                                                                    "broken_level": candle_4h["low"],
                                                                    "time": floored_5m_pb_time.isoformat()
                                                                }
                                                            ]
                                                        }
                                                        self.send_event(event_payload_5m)

                                                # swing_time = self.state.swing_low_time

                                                # if swing_time is not None:
                                                #     self.state.leg_buffer_4h = [
                                                #         c for c in self.state.leg_buffer_4h
                                                #         if c["time"] >= swing_time
                                                #     ]
                                                # else:
                                                #     print("[INFO] swing_low_time is None — keeping full leg_buffer_4h (seed phase)")

                                                self.state.candidate_high = None
                                                self.state.bearish_count = 0
                                                self.state.green_count=0
                                                print("leg buff", len(self.state.leg_buffer_4h))
                                                #print()
                                                
                                                # Call POI detection after pullback
                                                # For BULLISH: keep leg candles from the swing low price -> end
                                                swing_price = self.state.swing_low
                                                start_idx = next(
                                                    (
                                                        i for i, c in enumerate(self.state.leg_buffer_4h)
                                                        if (c.get("low") == swing_price) or (
                                                            isinstance(c.get("low"), (int, float)) and isinstance(swing_price, (int, float)) and abs(c.get("low") - swing_price) < 1e-8
                                                        )
                                                    ),
                                                    0,
                                                )
                                                sliced = self.state.leg_buffer_4h[start_idx:]
                                                swing_df = pd.DataFrame(sliced).set_index("time")
                                                self.state.leg_buffer_4h.clear()
                                                print("swing df len", len(swing_df))
                                                #print()
                                                self.state.active_pois = detect_pois_from_swing(
                                                    ohlc_df=swing_df,
                                                    trend=self.state.trend_4h,
                                                    pair=self.symbol,
                                                    choch_happened=self.state.trigger_choch_poi,
                                                    choch_level=self.state.choch_broken_level,
                                                    choch_time=self.state.choch_broken_time
                                                )
                                                
                                                # Reset CHOCH POI trigger after consumption
                                                self.state.trigger_choch_poi = False
                                                self.state.choch_broken_level = None
                                                self.state.choch_broken_time = None
                                                # print(f"[DEBUG] DETECTED {len(self.state.active_pois)} POIs in swing leg")
                                            

                                                liq_events = []
                                                ob_events = []

                                                for p in self.state.active_pois:
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

                                                if liq_events:
                                                    payload = {"symbol": self.symbol, "timeframe": "4H", "events": liq_events}
                                                    self.send_event(payload)

                                                if ob_events:
                                                    payload = {"symbol": self.symbol, "timeframe": "4H", "events": ob_events}
                                                    self.send_event(payload)
                                                
                                                mapped_pois = []

                                                for poi in self.state.active_pois:
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

                                                self.state.mapped_pois = mapped_pois
                                                self.buffer_5m_poi.clear()

                                        if self.state.pullback_confirmed:
                                            if self.state.swing_low and candle_4h["close"] < self.state.swing_low:
                                                if not is_historical:
                                                    print(f"[{self.symbol}] [CHOCH] BEARISH @ {candle_4h['time']}")
                                                    #print()
                                                self.state.bos_time_4h = candle_4h["time"]
                                                self.state.choch_level_4h = candle_4h["close"]
                                                self.state.h4_structure_event = "CHOCH"
                                                
                                                # Capture relevant swing high before clearing/resetting
                                                broken_swing_time = self.state.swing_low_time if self.state.swing_low_time else candle_4h["time"]
                                                
                                                # Store CHOCH POI details
                                                self.state.trigger_choch_poi = True
                                                self.state.choch_broken_level = self.state.swing_low
                                                self.state.choch_broken_time = broken_swing_time
                                                
                                                self.reset_on_4h_structure()
                                                
                                                # Calculate new swing high and its time from the leg
                                                if self.state.leg_buffer_4h:
                                                    max_candle = max(self.state.leg_buffer_4h, key=lambda c: c["high"])
                                                    self.state.swing_high = max_candle["high"]
                                                    self.state.swing_high_time = max_candle["time"]
                                                self.state.swing_high= self.state.candidate_high
                                                self.state.candidate_high = None
                                                broken_level = self.state.swing_low
                                                self.state.candidate_low = candle_4h["low"]
                                                self.state.trend_4h = "BEARISH"
                                                self.state.pullback_confirmed = False
                                                self.state.pullback_time = None
                                                self.state.bullish_count = 0
                                                self.state.bearish_count = 0
                                                self.state.green_count=0
                                                self.state.red_count=0

                                                
                                                if  not is_historical and broken_level is not None:

                                                    event_payload = {
                                                        "symbol": self.symbol,
                                                        "timeframe": "4h",
                                                        "events": [
                                                            {
                                                                "id": f"4H_CHOCH_{candle_4h['time'].strftime('%Y%m%d_%H%M')}",
                                                                "type": "CHOCH",
                                                                "broken_level": self.state.swing_low,
                                                                "time": broken_swing_time.isoformat()
                                                            }
                                                        ]
                                                    }
                                                    self.send_event(event_payload)

                                                self.buffer_5m.clear()  

                                        if self.state.pullback_confirmed:
                                            if self.state.trend_4h == "BULLISH" and self.state.swing_high is not None and candle_4h["close"] > self.state.swing_high:
                                                if not is_historical:
                                                    print(f"[{self.symbol}] [BOS] BULLISH @ {candle_4h['time']}")
                                                    #print()
                                                self.state.bos_level_4h = candle_4h["close"]
                                                self.state.bos_time_4h= candle_4h["time"]
                                                self.state.h4_structure_event="BOS"
                                                
                                                # Capture broken swing time
                                                broken_swing_time = self.state.swing_high_time if self.state.swing_high_time else candle_4h["time"]
                                                
                                                self.reset_on_4h_structure()                
                                                # 🔹 Calculate new swing LOW from old leg
                                                if self.state.leg_buffer_4h:
                                                    min_candle = min(self.state.leg_buffer_4h, key=lambda c: c["low"])
                                                    self.state.swing_low = min_candle["low"]
                                                    self.state.swing_low_time = min_candle["time"]
                                                self.state.pullback_confirmed = False
                                                self.state.pullback_time = None
                                                self.state.bullish_count = 0
                                                self.state.bearish_count = 0
                                                self.state.green_count=0
                                                self.state.red_count=0

                                                # 📡 Broadcast BOS
                                                if not is_historical:
                                                    event_payload = {
                                                        "symbol": self.symbol,
                                                        "timeframe": "4h",
                                                        "events": [
                                                            {
                                                                "id": f"4H_BOS_{candle_4h['time'].strftime('%Y%m%d_%H%M')}",
                                                                "type": "BOS",
                                                                "broken_level": self.state.swing_high,
                                                                "time": broken_swing_time.isoformat()
                                                            }
                                                        ]
                                                    }
                                                    self.send_event(event_payload)
                                                    
                                                    self.buffer_5m.clear()

                                    elif self.state.trend_4h == "BEARISH":
                                        if self.state.candidate_low is None or candle_4h["low"] < self.state.candidate_low:
                                            self.state.candidate_low = candle_4h["low"]
                                            self.state.candidate_low_time = candle_4h["time"]
                                            self.state.bullish_count = 0
                                            self.state.red_count=0

                                        if candle_4h["close"] > candle_4h["open"] and candle_4h["low"] > self.state.candidate_low:
                                            self.state.bullish_count += 1
                                        if self.state.bullish_count > 0 and self.state.bullish_count <= 10 and candle_4h["close"] < candle_4h["open"]:
                                            self.state.red_count+=1

                                        if self.state.swing_high and self.state.candidate_low:
                                            depth_ratio = (candle_4h["high"] - self.state.candidate_low) / max(self.state.swing_high - self.state.candidate_low, 1e-9)
                                            if self.state.pullback_confirmed==False and (self.state.bullish_count >= self.state.min_pullback_candles or ( depth_ratio >= self.state.pullback_pct and self.state.red_count>=6)):
                                                self.state.pullback_confirmed = True
                                                choch_5m=False
                                                self.state.pullback_time = candle_4h["time"]
                                                if not is_historical:
                                                    print(f"\n[PULLBACK] [4H BEARISH PB] CONFIRMED @ {self.state.pullback_time}")
                                                    #print()
                                                self.state.h4_structure_event=None
                                                self.state.swing_low = self.state.candidate_low
                                                self.state.swing_low_time = self.state.candidate_low_time
                                                self.state.bullish_count = 0
                                                self.state.red_count=0

                                                if self.state.pullback_confirmed and self.state.pullback_time and self.state.swing_low:
                                                    if not is_historical:
                                                        event_payload = {
                                                            "symbol": self.symbol,
                                                            "timeframe": "4h",
                                                            "events": [
                                                                {
                                                                    "id": f"4H_PB_{self.state.pullback_time.strftime('%Y%m%d_%H%M')}",
                                                                    "type": "PULLBACK_CONFIRMED",
                                                                    "broken_level": candle_4h["high"],
                                                                    "time": self.state.pullback_time.isoformat()
                                                                }
                                                            ]
                                                        }
                                                    self.send_event(event_payload)
                                                    swing_time = self.state.swing_high_time

                                                # if swing_time is not None:
                                                #     self.state.leg_buffer_4h = [
                                                #         c for c in self.state.leg_buffer_4h
                                                #         if c["time"] >= swing_time
                                                #     ]
                                                # else:
                                                #     print("[INFO] swing_high_time is None — keeping full leg_buffer_4h (seed phase)")
                                                                                                
                                                print("leg buff", len(self.state.leg_buffer_4h))
                                                #print()
                                                # For BEARISH: keep leg candles from the swing high price -> end
                                                swing_price = self.state.swing_high
                                                start_idx = next(
                                                    (
                                                        i for i, c in enumerate(self.state.leg_buffer_4h)
                                                        if (c.get("high") == swing_price) or (
                                                            isinstance(c.get("high"), (int, float)) and isinstance(swing_price, (int, float)) and abs(c.get("high") - swing_price) < 1e-8
                                                        )
                                                    ),
                                                    0,
                                                )
                                                sliced = self.state.leg_buffer_4h[start_idx:]
                                                swing_df = pd.DataFrame(sliced).set_index("time")
                                                self.state.leg_buffer_4h.clear()
                                                print("swing df len", len(swing_df))
                                                #print()
                                                self.state.active_pois = detect_pois_from_swing(
                                                    ohlc_df=swing_df,
                                                    trend="BEARISH",
                                                    pair=self.symbol,
                                                    choch_happened=self.state.trigger_choch_poi,
                                                    choch_level=self.state.choch_broken_level,
                                                    choch_time=self.state.choch_broken_time
                                                )
                                                
                                                # Reset CHOCH POI trigger after consumption
                                                self.state.trigger_choch_poi = False
                                                self.state.choch_broken_level = None
                                                self.state.choch_broken_time = None
                                                print(f"[DEBUG] DETECTED {len(self.state.active_pois)} POIs in BEARISH 4H swing leg")
                                                #print()

                                                liq_events = []
                                                ob_events = []

                                                for p in self.state.active_pois:
                                                    if p.get("time") is None or not hasattr(p["time"], "strftime"):
                                                        continue

                                                    ts_str = p["time"].strftime("%Y%m%d_%H%M")
                                                    iso_time = p["time"].isoformat()

                                                    if p["type"] == "LIQ":
                                                        liq_events.append({
                                                            "id": f"4H_POI_LIQ_{ts_str}",
                                                            "type": "POI-LIQ",
                                                            "price": p["price_high"] if p["price_high"] is not None else p["price_low"],
                                                            "time": iso_time,
                                                            "trend": "BEARISH",
                                                            "if_valid": True
                                                        })

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

                                                if liq_events:
                                                    payload = {
                                                        "symbol": self.symbol,
                                                        "timeframe": "4H",
                                                        "events": liq_events
                                                    }
                                                    self.send_event(payload)

                                                if ob_events:
                                                    payload = {
                                                        "symbol": self.symbol,
                                                        "timeframe": "4H",
                                                        "events": ob_events
                                                    }
                                                    self.send_event(payload)

                                                mapped_pois = []

                                                for poi in self.state.active_pois:
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

                                                    if poi["type"] == "OB":
                                                        mapped.update({
                                                            "price_low": poi["price_low"],
                                                            "price_high": poi["price_high"]
                                                        })

                                                    elif poi["type"] == "LIQ":
                                                        mapped.update({
                                                            "price": poi["price_high"] if poi["price_high"] is not None else poi["price_low"]
                                                        })

                                                    mapped_pois.append(mapped)

                                                self.state.mapped_pois = mapped_pois
                                                self.buffer_5m_poi.clear()

                                        if self.state.pullback_confirmed:
                                            if self.state.swing_high and candle_4h["close"] > self.state.swing_high:
                                                print(f"[{self.symbol}] [CHOCH] BULLISH @ {candle_4h['time']}")
                                                #print()
                                                self.state.bos_time_4h = candle_4h["time"]
                                                self.state.choch_level_4h = candle_4h["close"]
                                                self.state.h4_structure_event="CHOCH"
                                                
                                                # Capture relevant swing low before clearing/resetting
                                                broken_swing_time = self.state.swing_high_time if self.state.swing_high_time else candle_4h["time"]
                                                
                                                # Store CHOCH POI details
                                                self.state.trigger_choch_poi = True
                                                self.state.choch_broken_level = self.state.swing_high
                                                self.state.choch_broken_time = broken_swing_time
                                                
                                                self.reset_on_4h_structure()
                                                
                                                # Calculate new swing low and its time from the leg
                                                # if self.state.leg_buffer_4h:
                                                #     min_candle = min(self.state.leg_buffer_4h, key=lambda c: c["low"])
                                                #     self.state.swing_low = min_candle["low"]
                                                #     self.state.swing_low_time = min_candle["time"]
                                                self.state.swing_low=self.state.candidate_low
                                                self.state.candidate_high = candle_4h["high"]
                                                self.state.trend_4h = "BULLISH"
                                                self.state.pullback_confirmed = False
                                                self.state.pullback_time = None
                                                self.state.bullish_count = 0
                                                self.state.bearish_count = 0
                                                self.state.green_count=0
                                                self.state.red_count=0
                                                broken_level = self.state.swing_high
                                                if  broken_level is not None:

                                                    event_payload = {
                                                        "symbol": self.symbol,
                                                        "timeframe": "4h",
                                                        "events": [
                                                            {
                                                                "id": f"4H_CHOCH_{candle_4h['time'].strftime('%Y%m%d_%H%M')}",
                                                                "type": "CHOCH",
                                                                "broken_level": self.state.swing_high,
                                                                "time": broken_swing_time.isoformat()
                                                            }
                                                        ]
                                                    }
                                                    self.send_event(event_payload)

                                                self.buffer_5m.clear()  

                                        if self.state.pullback_confirmed:
                                            if self.state.trend_4h == "BEARISH" and self.state.swing_low is not None and candle_4h["close"] < self.state.swing_low:
                                                print(f"[{self.symbol}] [BOS] BEARISH @ {candle_4h['time']}")
                                                #print()
                                                self.state.bos_level_4h = candle_4h["close"]
                                                self.state.bos_time_4h = candle_4h["time"]
                                                self.state.h4_structure_event="BOS"
                                                
                                                # Capture broken swing time
                                                broken_swing_time = self.state.swing_low_time if self.state.swing_low_time else candle_4h["time"]
                                                
                                                self.reset_on_4h_structure()
                                                
                                                if self.state.leg_buffer_4h:
                                                    
                                                    max_candle = max(self.state.leg_buffer_4h, key=lambda c: c["high"])
                                                    self.state.swing_high = max_candle["high"]
                                                    self.state.swing_high_time = max_candle["time"]
                                                self.state.pullback_confirmed = False
                                                self.state.pullback_time = None
                                                self.state.bullish_count = 0
                                                self.state.bearish_count = 0
                                                self.state.green_count=0
                                                self.state.red_count=0

                                                event_payload = {
                                                    "symbol": self.symbol,
                                                    "timeframe": "4h",
                                                    "events": [
                                                        {
                                                            "id": f"4H_BOS_{candle_4h['time'].strftime('%Y%m%d_%H%M')}",
                                                            "type": "BOS",
                                                            "broken_level": self.state.swing_low,
                                                            "time": broken_swing_time.isoformat()
                                                        }
                                                    ]
                                                }
                                                self.send_event(event_payload)
                                             
                                                self.buffer_5m.clear()

                            # --------------------------------------------------
                            # 5M GATING LOGIC
                            # --------------------------------------------------

                            if not self.state.pullback_confirmed or not self.state.mapped_pois or len(self.state.mapped_pois) == 0:
                                continue

                            bull_candle_5m = candle_5m["close"] > candle_5m["open"]
                            bear_candle_5m = candle_5m["close"] < candle_5m["open"]
                            
                            # --------------------------------------------------
                            # 5M CHOCH & BOS LOGIC after PB CONFIRMED
                            # --------------------------------------------------
                            if self.state.pullback_confirmed:
                                if self.state.candidate_high_5m is None:
                                    self.state.market_trend_5m = "BULLISH"
                                    self.state.candidate_high_5m = candle_5m["high"]
                                    self.state.candidate_high_5m_time = candle_5m["time"]
                                    self.state.pullback_count_5m = 0
                                    if self.state.swing_low_5m is None:
                                        self.state.swing_low_5m = candle_5m["low"]
                                        self.state.swing_low_5m_time = candle_5m["time"]
                                    continue

                                if self.state.market_trend_5m == "BULLISH":
                                    if bear_candle_5m and (self.state.pullback_count_5m >= 0 and self.state.pullback_count_5m < 3):
                                        self.state.pullback_count_5m += 1

                                    retrace = (self.state.candidate_high_5m - candle_5m["low"]) / max(self.state.candidate_high_5m - self.state.swing_low_5m, 1e-9)
                                    valid_pullback_5m = False
                                    if not self.state.pullback_confirmed_5m:
                                        valid_pullback_5m = self.state.pullback_count_5m >= 3 or retrace >= 0.99
                                        if valid_pullback_5m:
                                             self.state.pullback_confirmed_5m = True
                                             reason = "COUNT" if self.state.pullback_count_5m >= 3 else "PCT"

                                    if candle_5m["high"] > self.state.candidate_high_5m and not self.state.pullback_confirmed_5m:
                                        self.state.candidate_high_5m = candle_5m["high"]
                                        self.state.pullback_count_5m = 0


                                    if self.state.pullback_confirmed_5m:
                                        self.state.swing_high_5m=self.state.candidate_high_5m
                                        self.state.swing_high_5m_time = self.state.candidate_high_5m_time
                                        #print(f"[DEBUG] 5M Swing High set: {self.state.swing_high_5m} @ {self.state.swing_high_5m_time} (Pullback Confirmed)")
                                        self.state.buffer_5m_sl.append(candle_5m)
                                        # BOS 5m 
                                        if candle_5m["high"] > self.state.candidate_high_5m:
                                            swing_candle = min(
                                                self.state.buffer_5m_sl,
                                                key=lambda c: c["low"]
                                            )
                                            if self.state.active_poi is not None:
                                                self.state.bos_count_5m += 1
                                                #print(f"[DEBUG] 5m BOS count updated (BULLISH): {self.state.bos_count_5m} | Time: {candle_5m['time']} | Level: {self.state.candidate_high_5m}")

                                            self.state.swing_low_5m = swing_candle["low"]
                                            #print("swing low after pb bullish", self.state.swing_low_5m)
                                            self.state.swing_low_5m_time = swing_candle["time"]
                                            self.state.protected_5m_point = self.state.swing_low_5m
                                            self.state.protected_5m_time = self.state.swing_low_5m_time
                                            # 📡 Broadcast 5M BOS
                                            # event_payload = {
                                            #     "symbol": self.symbol,
                                            #     "timeframe": "5m",
                                            #     "events": [
                                            #         {
                                            #             "id": f"5m_BOS_{candle_5m['time'].strftime('%Y%m%d_%H%M')}",
                                            #             "type": "BOS",
                                            #             "broken_level": self.state.candidate_low_5m,
                                            #             "time": self.state.candidate_low_5m_time.isoformat()
                                            #         }
                                            #     ]
                                            # }
                                            # self.send_event(event_payload)

                                            self.state.candidate_high_5m = candle_5m["high"]
                                            self.state.candidate_high_5m_time = candle_5m["time"]
                                            self.state.pullback_count_5m = 0
                                            self.state.pullback_confirmed_5m = False
                                            self.state.buffer_5m_sl.clear()

                                        # CHOCH 5m 
                                        #print("checking choch bullish", candle_5m["low"], self.state.swing_low_5m)
                                        if candle_5m["low"] < self.state.swing_low_5m:

                                            self.state.swing_high_5m = self.state.candidate_high_5m
                                            self.state.swing_high_5m_time = self.state.candidate_high_5m_time
                                            #print(f"[DEBUG] 5M Swing High set: {self.state.swing_high_5m} @ {self.state.swing_high_5m_time} (CHOCH: Low {candle_5m['low']} < SwingLow {self.state.swing_low_5m})")
                                            self.state.market_trend_5m = "BEARISH"
                                            self.state.pullback_count_5m = 0
                                            self.state.pullback_confirmed_5m = False
                                            self.state.candidate_low_5m = candle_5m["low"]
                                            self.state.candidate_low_5m_time = candle_5m["time"]
                                            self.state.bos_count_5m=0
                                            
                                            self.state.buffer_5m_sl.clear()

                                if self.state.market_trend_5m == "BEARISH":
                                    if bull_candle_5m and (self.state.pullback_count_5m >= 0 and self.state.pullback_count_5m < 3):
                                        self.state.pullback_count_5m += 1

                                    retrace = (candle_5m["high"] - self.state.candidate_low_5m) / max(self.state.swing_high_5m - self.state.candidate_low_5m, 1e-9)
                                    valid_pullback_5m = False
                                    if not self.state.pullback_confirmed_5m:
                                        valid_pullback_5m = self.state.pullback_count_5m >= 3 or retrace >= 0.99
                                        if valid_pullback_5m:
                                             self.state.pullback_confirmed_5m = True
                                             reason = "COUNT" if self.state.pullback_count_5m >= 3 else "PCT"

                                    if candle_5m["low"] < self.state.candidate_low_5m and not self.state.pullback_confirmed_5m:
                                        self.state.candidate_low_5m = candle_5m["low"]
                                        self.state.pullback_count_5m = 0



                                    if self.state.pullback_confirmed_5m:
                                        self.state.swing_low_5m=self.state.candidate_low_5m
                                        self.state.swing_low_5m_time = self.state.candidate_low_5m_time
                                        #print(f"[DEBUG] 5M Swing Low set: {self.state.swing_low_5m} @ {self.state.swing_low_5m_time} (Pullback Confirmed)")
                                        
                                        self.state.buffer_5m_sh.append(candle_5m)
                                        # BOS 5m (BEARISH VERSION)
                                        if candle_5m["low"] < self.state.candidate_low_5m:
                                            swing_candle = max(
                                                self.state.buffer_5m_sh,
                                                key=lambda c: c["high"]
                                            )
                                            if self.state.active_poi is not None:
                                                self.state.bos_count_5m += 1
                                                #print(f"[DEBUG] 5m BOS count updated (BEARISH): {self.state.bos_count_5m} | Time: {candle_5m['time']} | Level: {self.state.candidate_low_5m}")

                                            self.state.swing_high_5m = swing_candle["high"]
                                            self.state.swing_high_5m_time = swing_candle["time"]
                                            self.state.protected_5m_point = self.state.swing_high_5m
                                            self.state.protected_5m_time = self.state.swing_high_5m_time
                                            # 📡 Broadcast 5M BOS
                                            # event_payload = {
                                            #     "symbol": self.symbol,
                                            #     "timeframe": "5m",
                                            #     "events": [
                                            #         {
                                            #             "id": f"5m_BOS_{candle_5m['time'].strftime('%Y%m%d_%H%M')}",
                                            #             "type": "BOS",
                                            #             "broken_level": self.state.candidate_low_5m,
                                            #             "time": self.state.candidate_low_5m_time.isoformat()
                                            #         }
                                            #     ]
                                            # }
                                            # self.send_event(event_payload)

                                            self.state.candidate_low_5m = candle_5m["low"]
                                            self.state.candidate_low_5m_time = candle_5m["time"]
                                            self.state.pullback_count_5m = 0
                                            self.state.pullback_confirmed_5m = False
                                            self.state.buffer_5m_sh.clear()

                                        # CHOCH 5m (BEARISH VERSION)
                                        if candle_5m["high"] > self.state.swing_high_5m:

                                            self.state.swing_low_5m = self.state.candidate_low_5m
                                            self.state.swing_low_5m_time = self.state.candidate_low_5m_time
                                            #print(f"[DEBUG] 5M Swing Low set: {self.state.swing_low_5m} @ {self.state.swing_low_5m_time} (CHOCH: High {candle_5m['high']} > SwingHigh {self.state.swing_high_5m})")
                                            self.state.market_trend_5m = "BULLISH"
                                            self.state.pullback_count_5m = 0
                                            self.state.bos_count_5m=0
                                            self.state.pullback_confirmed_5m = False
                                            self.state.candidate_high_5m = candle_5m["high"]
                                            self.state.candidate_high_5m_time = candle_5m["time"]
                                            self.state.buffer_5m_sh.clear()

 

                            if self.state.trend_4h=="BULLISH":                
                                # # --------------------------------------------------
                                # 5M POI TAP CHECK (Realtime)
                                # --------------------------------------------------
                                if self.state.mapped_pois and not self.state.poi_tapped and self.state.active_poi is None:
                                    
                                    # Check POI TAP omly ONLY IF POI IS VALID
                                    for poi in self.state.mapped_pois:
                                        if not poi["if_valid"]:
                                            continue

                                        if poi["type"] == "OB":
                                            if candle_5m["low"] <= poi["price_high"] :
                                                self.state.poi_tapped = True
                                                self.state.active_poi = poi
                                                self.state.bos_count_5m = 0
                                                self.state.poi_tapped_level = candle_5m["low"]
                                                self.state.poi_tapped_time = candle_5m["time"]
                                                print(f"[TARGET] POI TAPPED (OB) @ {candle_5m['time']}")
                                                #print()
                                                poi["if_valid"]=False
                                                break

                                        elif poi["type"] == "LIQ":
                                            if candle_5m["low"] <= poi["price"]:
                                                self.state.poi_tapped = True
                                                self.state.active_poi = poi
                                                self.state.bos_count_5m = 0
                                                self.state.poi_tapped_level = candle_5m["low"]
                                                self.state.poi_tapped_time = candle_5m["time"]
                                                print(f"[TARGET] POI TAPPED (LIQ) @ {candle_5m['time']}")
                                                #print()
                                                poi["if_valid"]=False
                                                break


                                    if self.state.poi_tapped:
                                        # 📡 Broadcast POI-TAP Events
                                        ts_str = candle_5m['time'].strftime('%Y%m%d_%H%M')
                                        iso_time_5m = candle_5m['time'].isoformat()
                                        
                                        # 5M Event
                                        event_manager.send_threadsafe({
                                            "symbol": self.symbol,
                                            "timeframe": "5m",
                                            "events": [
                                                {
                                                    "id": f"5m_POI_TAP_{ts_str}",
                                                    "type": "POI-TAP",
                                                    "POI_TAP": float(candle_5m["low"]),
                                                    "time": iso_time_5m
                                                }
                                            ]
                                        })

                                        # 4H Event
                                        floored_4h_time = candle_5m["time"].replace(
                                            hour=(candle_5m["time"].hour // 4) * 4,
                                            minute=0,
                                            second=0,
                                            microsecond=0
                                        )
                                        current_4h_low = min(c["low"] for c in self.curr_4h_bucket)
                                        
                                        event_manager.send_threadsafe({
                                            "symbol": self.symbol,
                                            "timeframe": "4h",
                                            "events": [
                                                {
                                                    "id": f"4H_POI_TAP_{floored_4h_time.strftime('%Y%m%d_%H%M')}",
                                                    "type": "POI-TAP",
                                                    "POI_TAP": float(current_4h_low),
                                                    "time": floored_4h_time.isoformat()
                                                }
                                            ]
                                        })

                                        active_poi = self.state.active_poi
                                        next_poi = None

                                        # FIND NEXT VALID POI
                                        for poi in self.state.mapped_pois:
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
                                        
                                        elif p0_type == "LIQ" and (active_poi["price"] == self.state.swing_high or active_poi["price"] == self.state.swing_low):
                                            self.state.no_invalidation = True
                                            invalidation_level = None

                                        else:    
                                            if p0_type == "OB":
                                                invalidation_level = (active_poi["price_high"] + self.state.swing_low) / 2
                                            else:
                                                invalidation_level = (active_poi["price"] + self.state.swing_low) / 2

                                # --------------------------------------------------    
                                # 5M CHOCH CHECK & TRADE SETUP (Realtime)
                                # --------------------------------------------------   
                                if not self.state.choch_5m and self.state.active_poi :
                                    if not self.state.no_invalidation:
                                        if candle_5m["low"]<= invalidation_level or self.state.bos_count_5m>=2:
                                            self.state.active_poi=None
                                            self.state.poi_tapped=False
                                            self.state.bos_count_5m=0
                                            print("invalidation level hit, removing active poi")
                                            continue
                                    else:
                                        if self.state.bos_count_5m>=2:
                                            self.state.active_poi=None
                                            self.state.poi_tapped=False
                                            self.state.bos_count_5m=0
                                            print("invalidation level hit, removing active poi that is swing poi")

                                    if candle_5m["high"] > self.state.swing_high_5m :
                                        self.state.choch_5m=True
                                        self.state.trade_active = True
                                        self.state.current_poi=self.state.active_poi
                                        self.state.active_poi=None
                                        self.state.bos_count_5m=0
                                        self.state.poi_tapped=False
                                        print(f"[{self.symbol}] [START] 5M trade CHOCH @ {self.state.swing_high_5m_time} | Broken High: {self.state.swing_high_5m}")
                                        #print()
                                        # 📡 Broadcast 5M CHOCH
                                        event_payload = {
                                            "symbol": self.symbol,
                                            "timeframe": "5m",
                                            "events": [
                                                {
                                                    "id": f"5m_CHOCH_{self.state.swing_high_5m_time.strftime('%Y%m%d_%H%M')}",
                                                    "type": "CHOCH",
                                                    "broken_level": self.state.swing_high_5m,
                                                    "time": self.state.swing_high_5m_time.isoformat()
                                                }
                                            ]
                                        }
                                        self.send_event(event_payload)
                                    # --------------------------------------------------
                                    # TRADE SETUP (CHOCH + POI)
                                    # --------------------------------------------------
                                    if self.state.choch_5m and self.state.trade_active and not self.state.trade_planned:
                                        self.state.choch_5m=False            
                                        if self.state.trend_4h == "BULLISH":
                                            range_high = self.state.swing_high_5m          # CHOCH candle high
                                            range_low = self.state.swing_low_5m            # last bearish swing low
                                            direction = "BUY"

                                        # Safety check
                                        if range_high is None or range_low is None:
                                            print("Invalid range for trade setup, skipping...")
                                            continue

                                        entry = (range_high + range_low) / 2
                                        pip = 0.0001
                                        if direction == "BUY":
                                            stop_loss = range_low - 4 * pip
                                            risk = entry - stop_loss
                                            take_profit = entry + 3 * risk

                                        if risk <= 0:
                                            continue

                                        self.state.trade = {
                                            "direction": direction,
                                            "entry": float(entry),
                                            "sl": float(stop_loss),
                                            "tp": float(take_profit),
                                            "rr": 3.0,
                                            "htf_trend": self.state.trend_4h,
                                            "poi_type": self.state.current_poi["type"],
                                            "poi_price_low": self.state.current_poi.get("price_low"),
                                            "poi_price_high": self.state.current_poi.get("price_high"),
                                            "poi_time": self.state.poi_tapped_time,
                                            "choch_time": candle_5m["time"],
                                            "range_high": float(range_high),
                                            "range_low": float(range_low),
                                            "planned_time": candle_5m["time"],
                                            "status": "PLANNED",
                                        }
                                        
                                        self.state.trade_planned = True

                                        ts_str = candle_5m['time'].strftime('%Y%m%d_%H%M')
                                        iso_start = candle_5m['time'].isoformat()
                                        iso_end = (candle_5m['time'] + pd.Timedelta(minutes=25)).isoformat()
                                        
                                        retr_event = {
                                            "symbol": self.symbol,
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
                                        
                                        plan_event = {
                                            "symbol": self.symbol,
                                            "timeframe": "5m",
                                            "events": [
                                                {
                                                    "id": f"5m_TRADE_{ts_str}",
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
                                        
                                        self.send_event(retr_event)
                                        self.send_event(plan_event)

                                        print(f"[{self.symbol}] [START] TRADE PLANNED & STORED")
                                        #print()
                                        print("Trade Details:", self.state.trade)
                                        #print()

                                # --------------------------------------------------
                                # TRADE MANAGEMENT (BUY ONLY - Realtime 5M)
                                # --------------------------------------------------
                                if self.state.trade_planned and self.state.trade is not None:

                                        trade = self.state.trade

                                        if trade["direction"] == "BUY":
                                            entry = trade["entry"]
                                            sl = trade["sl"]
                                            tp = trade["tp"]

                                            candle_high = candle_5m["high"]
                                            candle_low = candle_5m["low"]
                                            candle_time = candle_5m["time"]

                                            if not self.state.entry_filled:
                                                entry_filled_this_candle = False
                                                if candle_low <= entry <= candle_high:
                                                    entry_filled_this_candle = True

                                                # 2% Invalidation Check (Long)  
                                                if not entry_filled_this_candle and (candle_high >= entry * 0.02):
                                                    print(f"[{self.symbol}] [INVALIDATE] Long Trade Invalidated (Price moved >2% to TP side) at {candle_time}")
                                                    self.state.trade = None
                                                    self.state.trade_planned = False
                                                    self.state.entry_filled = False
                                                    self.state.invalidation += 1
                                                    print("Invalidation count:", self.state.invalidation)
                                                    continue

                                                if entry_filled_this_candle:
                                                    self.state.entry_filled = True
                                                    trade["status"] = "OPEN"
                                                    trade["entry_time"] = candle_time
                                                    print(f"[{self.symbol}] [OPEN] BUY ENTRY FILLED @ {entry} | {candle_time}")

                                            else:
                                                if candle_low <= sl:
                                                    print(f"[{self.symbol}] [FAIL] BUY SL HIT @ {sl}")
                                                    trade["status"] = "SL"
                                                    trade["exit_time"] = candle_time
                                                    trade["exit_price"] = sl
                                                    self.save_trade_to_db(trade["entry_time"], "BUY", "SL", trade["entry"], sl, -100)
                                                    print("trade saved to db after SL")
                                                    self.state.trade = None
                                                    self.state.trade_planned = False
                                                    self.state.entry_filled = False
                                                    continue

                                                elif candle_high >= tp:
                                                    print(f"[{self.symbol}] [SUCCESS] BUY TP HIT @ {tp}")
                                                    trade["status"] = "TP"
                                                    trade["exit_time"] = candle_time
                                                    trade["exit_price"] = tp
                                                    self.save_trade_to_db(trade["entry_time"], "BUY", "WIN", trade["entry"], tp, 100)
                                                    print("trade saved to db after TP")
                                                    self.state.trade = None
                                                    self.state.trade_planned = False
                                                    self.state.entry_filled = False
                                                    continue

                            if self.state.trend_4h == "BEARISH":
                                # # --------------------------------------------------
                                # 5M POI TAP CHECK (MIRRORED FOR BEARISH)
                                # --------------------------------------------------
                                if self.state.mapped_pois and not self.state.poi_tapped and self.state.active_poi is None:
                                    for poi in self.state.mapped_pois:
                                        if not poi["if_valid"]:
                                            continue

                                        if poi["type"] == "OB":
                                            # MIRRORED: For BEARISH trend, check if price touches OB from above
                                            if candle_5m["high"] >= poi["price_low"] and candle_5m["low"] <= poi["price_high"]:
                                                self.state.poi_tapped = True
                                                self.state.active_poi = poi
                                                self.state.bos_count_5m = 0
                                                self.state.poi_tapped_level = candle_5m["high"]  # MIRRORED: Use high instead of low
                                                self.state.poi_tapped_time = candle_5m["time"]
                                                print(f"[TARGET] POI TAPPED (OB) @ {candle_5m['time']}")
                                                #print()
                                                poi["if_valid"] = False
                                                break

                                        elif poi["type"] == "LIQ":
                                            # MIRRORED: For BEARISH trend, check if price sweeps LIQ from above
                                            if candle_5m["high"] >= poi["price"]:
                                                self.state.poi_tapped = True
                                                self.state.active_poi = poi
                                                self.state.bos_count_5m = 0
                                                self.state.poi_tapped_level = candle_5m["high"]  # MIRRORED: Use high instead of low
                                                self.state.poi_tapped_time = candle_5m["time"]
                                                print(f"[TARGET] POI TAPPED (LIQ) @ {candle_5m['time']}")
                                                #print()
                                                poi["if_valid"] = False
                                                break

                                    if self.state.poi_tapped:
                                        # 📡 Broadcast POI-TAP Events
                                        ts_str = candle_5m['time'].strftime('%Y%m%d_%H%M')
                                        iso_time_5m = candle_5m['time'].isoformat()
                                        
                                        # 5M Event
                                        event_manager.send_threadsafe({
                                            "symbol": self.symbol,
                                            "timeframe": "5m",
                                            "events": [
                                                {
                                                    "id": f"5m_POI_TAP_{ts_str}",
                                                    "type": "POI-TAP",
                                                    "POI_TAP": float(candle_5m["high"]),
                                                    "time": iso_time_5m
                                                }
                                            ]
                                        })

                                        # 4H Event
                                        floored_4h_time = candle_5m["time"].replace(
                                            hour=(candle_5m["time"].hour // 4) * 4,
                                            minute=0,
                                            second=0,
                                            microsecond=0
                                        )
                                        current_4h_high = max(c["high"] for c in self.curr_4h_bucket)
                                        
                                        event_manager.send_threadsafe({
                                            "symbol": self.symbol,
                                            "timeframe": "4h",
                                            "events": [
                                                {
                                                    "id": f"4H_POI_TAP_{floored_4h_time.strftime('%Y%m%d_%H%M')}",
                                                    "type": "POI-TAP",
                                                    "POI_TAP": float(current_4h_high),
                                                    "time": floored_4h_time.isoformat()
                                                }
                                            ]
                                        })
                                        active_poi = self.state.active_poi

                                        next_poi = None
                                        for poi in self.state.mapped_pois:
                                            if not poi["if_valid"]:
                                                continue
                                            else:
                                                next_poi = poi
                                                break

                                        p0_type = active_poi["type"]

                                        if next_poi:
                                            p1_type = next_poi["type"]
                                            if p0_type == "OB" and p1_type == "OB":
                                                invalidation_level = (active_poi["price_low"] + next_poi["price_low"]) / 2
                                            elif p0_type == "OB" and p1_type == "LIQ":
                                                invalidation_level = (active_poi["price_low"] + next_poi["price"]) / 2
                                            elif p0_type == "LIQ" and p1_type == "LIQ":
                                                invalidation_level = (active_poi["price"] + next_poi["price"]) / 2
                                            elif p0_type == "LIQ" and p1_type == "OB":
                                                invalidation_level = (active_poi["price"] + next_poi["price_low"]) / 2
                                        else:
                                            if p0_type == "OB":
                                                invalidation_level = (active_poi["price_low"] + self.state.swing_high) / 2
                                            else:
                                                invalidation_level = (active_poi["price"] + self.state.swing_high) / 2

                                # --------------------------------------------------    
                                # 5M CHOCH CHECK & TRADE SETUP (MIRRORED FOR BEARISH)  
                                # --------------------------------------------------
                                if not self.state.choch_5m and self.state.active_poi:
                                    # MIRRORED: Check if price goes above invalidation level
                                    if not self.state.no_invalidation:
                                        if candle_5m["high"] >= invalidation_level or self.state.bos_count_5m >= 2:
                                            self.state.active_poi = None
                                            self.state.poi_tapped = False
                                            self.state.bos_count_5m = 0
                                            print("invalidation level hit, removing active poi")
                                            continue
                                    
                                    else:
                                        if self.state.bos_count_5m>=2:
                                            self.state.active_poi=None
                                            self.state.poi_tapped=False
                                            self.state.bos_count_5m=0
                                            print("invalidation level hit, removing active poi that is swing poi")
                                        
                                    # MIRRORED: For BEARISH, check BEARISH CHOCH (price breaks below swing_low)
                                    if candle_5m["low"] < self.state.swing_low_5m:
                                        self.state.choch_5m = True
                                        self.state.trade_active = True
                                        self.state.current_poi=self.state.active_poi
                                        self.state.active_poi = None
                                        self.state.bos_count_5m = 0
                                        self.state.poi_tapped = False
                                        print(f"[{self.symbol}] [START] 5M trade BEARISH CHOCH @ {self.state.swing_low_5m_time} | Broken Low: {self.state.swing_low_5m}")
                                        #print()
                                        
                                        # 📡 Broadcast 5M CHOCH (BEARISH VERSION)
                                        event_payload = {
                                            "symbol": self.symbol,
                                            "timeframe": "5m",
                                            "events": [
                                                {
                                                    "id": f"5m_CHOCH_{self.state.swing_low_5m_time.strftime('%Y%m%d_%H%M')}",
                                                    "type": "CHOCH",
                                                    "broken_level": self.state.swing_low_5m,  # MIRRORED: Use low instead of high
                                                    "time": self.state.swing_low_5m_time.isoformat()
                                                }
                                            ]
                                        }
                                        self.send_event(event_payload)

                                    # --------------------------------------------------
                                    # TRADE SETUP (CHOCH + POI) - MIRRORED FOR BEARISH
                                    # --------------------------------------------------
                                    if self.state.choch_5m and self.state.trade_active and not self.state.trade_planned:
                                        self.state.choch_5m = False
                        
                                        if self.state.trend_4h == "BEARISH":  # CHANGED TO BEARISH
                                            range_high = self.state.swing_high_5m  # Last bullish swing high
                                            range_low = self.state.swing_low_5m    # CHOCH candle low
                                            direction = "SELL"  # MIRRORED: SELL instead of BUY

                                        if range_high is None or range_low is None:
                                            print("❌ Invalid range — trade skipped")
                                            continue

                                        entry = (range_high + range_low) / 2
                                        pip = 0.0001

                                        if direction == "SELL":  # MIRRORED
                                            stop_loss = range_high + 4 * pip  # MIRRORED: Above range
                                            risk = stop_loss - entry  # MIRRORED: Risk calculation
                                            take_profit = entry - 3 * risk  # MIRRORED: Downwards target

                                        if risk <= 0:
                                            continue

                                        self.state.trade = {
                                            "direction": direction,
                                            "entry": float(entry),
                                            "sl": float(stop_loss),
                                            "tp": float(take_profit),
                                            "rr": 3.0,
                                            "htf_trend": self.state.trend_4h,
                                            "poi_type": self.state.current_poi["type"],
                                            "poi_price_low": self.state.current_poi.get("price_low"),
                                            "poi_price_high": self.state.current_poi.get("price_high"),
                                            "poi_time": self.state.poi_tapped_time,
                                            "choch_time": candle_5m["time"],
                                            "range_high": float(range_high),
                                            "range_low": float(range_low),
                                            "planned_time": candle_5m["time"],
                                            "status": "PLANNED",
                                        }

                                        self.state.trade_planned = True

                                        ts_str = candle_5m['time'].strftime('%Y%m%d_%H%M')
                                        iso_start = candle_5m['time'].isoformat()
                                        iso_end = (candle_5m['time'] + pd.Timedelta(minutes=25)).isoformat()
                                        
                                        retr_event = {
                                            "symbol": self.symbol,
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
                                        
                                        plan_event = {
                                            "symbol": self.symbol,
                                            "timeframe": "5m",
                                            "events": [
                                                {
                                                    "id": f"5m_TRADE_{ts_str}",
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
                                        
                                        self.send_event(retr_event)
                                        self.send_event(plan_event)

                                        print(f"[{self.symbol}] [START] TRADE PLANNED & STORED")
                                        #print()
                                        print("Trade Details:", self.state.trade)
                                        #print()

                                # --------------------------------------------------
                                # TRADE MANAGEMENT (SELL ONLY - Realtime 5M) - MIRRORED
                                # --------------------------------------------------
                                if self.state.trade_planned and self.state.trade is not None:
                                    trade = self.state.trade

                                    if trade["direction"] == "SELL":
                                        entry = trade["entry"]
                                        sl = trade["sl"]
                                        tp = trade["tp"]

                                        candle_high = candle_5m["high"]
                                        candle_low = candle_5m["low"]
                                        candle_time = candle_5m["time"]

                                        if not self.state.entry_filled:
                                            entry_filled_this_candle = False
                                            if candle_low <= entry <= candle_high:
                                                entry_filled_this_candle = True
                                            
                                            # 2% Invalidation Check (Short)
                                            if not entry_filled_this_candle and (candle_low <= entry * 0.98):
                                                print(f"[{self.symbol}] [INVALIDATE] Short Trade Invalidated (Price moved >2% to TP side) at {candle_time}")
                                                self.state.trade = None
                                                self.state.trade_planned = False
                                                self.state.entry_filled = False
                                                self.state.invalidation += 1
                                                print("Invalidation count:", self.state.invalidation)
                                                continue

                                            if entry_filled_this_candle:
                                                self.state.entry_filled = True
                                                trade["status"] = "OPEN"
                                                trade["entry_time"] = candle_time
                                                print(f"[{self.symbol}] [OPEN] SELL ENTRY FILLED @ {entry} | {candle_time}")

                                        else:
                                            # STOP LOSS (SELL VERSION)
                                            if candle_high >= sl:
                                                print(f"[{self.symbol}] [FAIL] SELL SL HIT @ {sl}")
                                                trade["status"] = "SL"
                                                trade["exit_time"] = candle_time
                                                trade["exit_price"] = sl

                                                self.save_trade_to_db(trade["entry_time"], "SELL", "SL", trade["entry"], sl, -100)
                                                print("trade saved to db after SL")
                                                self.state.trade = None
                                                self.state.trade_planned = False
                                                self.state.entry_filled = False
                                                continue

                                            # TAKE PROFIT (SELL VERSION)
                                            elif candle_low <= tp:
                                                print(f"[{self.symbol}] [SUCCESS] SELL TP HIT @ {tp}")
                                                trade["status"] = "TP"
                                                trade["exit_time"] = candle_time
                                                trade["exit_price"] = tp
                                                self.save_trade_to_db(trade["entry_time"], "SELL", "WIN", trade["entry"], tp, 100)
                                                print("trade saved to db after TP")
                                                self.state.trade = None
                                                self.state.trade_planned = False
                                                self.state.entry_filled = False
                                                continue

                    except ValueError as ve:
                        print(f"[WARN] ValueError in loop: {ve}")
                        continue
        except Exception as e:
            print(f"[ERROR] Error in Trading Engine ({self.symbol}): {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.running = False
            print(f"[STOP] Trading Engine ({self.symbol}) stopped.")

    def stop(self):
        self.running = False


# ==================================================
# ENGINE MANAGER
# ==================================================
class EngineManager:
    def __init__(self):
        self.engines: Dict[str, TradingEngine] = {}
        self.threads: Dict[str, threading.Thread] = {}
        self.lock = threading.Lock()

    def start_engine(self, symbol: str):
        with self.lock:
    
            if symbol in self.engines and self.threads[symbol].is_alive():
                print(f"[SKIP] Engine already running for {symbol}")
                return

            print(f"[START] Starting Trading Engine for {symbol}...")
            engine = TradingEngine(symbol)
            thread = threading.Thread(target=engine.run, daemon=True, name=f"Engine-{symbol}")
            
            self.engines[symbol] = engine
            self.threads[symbol] = thread
            thread.start()

    def stop_engine(self, symbol: str):
        with self.lock:
            if symbol in self.engines:
                print(f"[STOP] Stopping Engine for {symbol}...")
                self.engines[symbol].stop()
                if threading.current_thread() != self.threads.get(symbol):
                    self.threads[symbol].join()
                
                self.engines.pop(symbol, None)
                self.threads.pop(symbol, None)

    def stop_all_engines(self):
        print("[STOP] Stopping all trading engines...")
        with self.lock:
            symbols = list(self.engines.keys())
            for symbol in symbols:
                self.stop_engine(symbol)
        print("[DONE] All engines stopped.")

manager = EngineManager()

def start_engine(symbol: str):
    manager.start_engine(symbol)

# ==================================================
# LEGACY MAIN (FOR DIRECT EXECUTION)
# ==================================================
def main():
    while event_loop is None:
        time.sleep(0.1)

    print("🔌 Initializing Event & WS Managers with FastAPI loop...")
    ws_manager.set_loop(event_loop)
    event_manager.set_loop(event_loop)
    manager.start_engine("EURUSD")
    while True:
        time.sleep(1)

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    event_loop = loop
    main()