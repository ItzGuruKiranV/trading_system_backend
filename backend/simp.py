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

