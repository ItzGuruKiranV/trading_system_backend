# debug/plot_5m.py - PLOTS YOUR ACTUAL DATA

import finplot as fplt
import pandas as pd

def plot_5m_legs(all_legs_event_logs, df_5m, chunk_size=5):
    """Plots ALL swing_state events → POIs, swings, structure breaks."""
    
    if not all_legs_event_logs:
        print("[plot_5m_legs] ⚠️ No events")
        return
    
    print(f"[plot_5m_legs] 📊 Events: {len(all_legs_event_logs)}")
    print(f"[plot_5m_legs] Sample event: {all_legs_event_logs[0].event if hasattr(all_legs_event_logs[0], 'event') else 'NO EVENT'}")
    
    # Prep df_5m
    df_5m = df_5m.copy().sort_index()
    if not isinstance(df_5m.index, pd.DatetimeIndex):
        df_5m.index = pd.to_datetime(df_5m.index)
    
    # ✅ PLOT ALL EVENTS (no filtering)
    for i in range(0, len(all_legs_event_logs), chunk_size):
        chunk = all_legs_event_logs[i:i + chunk_size]
        
        # Chunk time range from events
        times = []
        for event in chunk:
            if hasattr(event, 'time'):
                times.append(event.time)
            elif hasattr(event, 'index') and isinstance(event.index, int):
                times.append(df_5m.index[event.index])
        
        if times:
            start_time = min(times)
            end_time = max(times)
        else:
            start_time, end_time = df_5m.index[0], df_5m.index[-1]
        
        # Create plot
        ax = fplt.create_plot(f"5M SMC Debug {i+1}-{i+len(chunk)} ({all_legs_event_logs[i].event})")
        fplt.candlestick_ochl(df_5m[['open', 'close', 'high', 'low']], ax=ax)
        
        # Plot each event
        for j, event in enumerate(chunk):
            try:
                # Convert namedtuple/dataclass → dict
                event_dict = vars(event) if hasattr(event, '__dict__') else event.__dict__
                
                event_name = getattr(event, 'event', 'UNKNOWN')
                
                # 1️⃣ POI BOX (priority)
                if hasattr(event, 'active_poi') and event.active_poi:
                    poi = event.active_poi
                    poi_time = poi.get('time') or poi.get('start_5m_time')
                    rect_start = pd.to_datetime(poi_time)
                    rect_end = event.time
                    low = poi.get('price_low')
                    high = poi.get('price_high')
                    poi_type = poi.get('type', 'POI')
                    
                    if low and high and rect_start <= rect_end:
                        color = 'cyan' if poi_type.upper() == 'OB' else 'yellow'
                        fplt.add_rect((rect_start, low), (rect_end, high), 
                                    color=color, width_fill=0.4, ax=ax, text=f"{poi_type}")
                        print(f"✅ POI {poi_type}: {low:.5f}-{high:.5f}")
                
                # 2️⃣ SWING BOX
                elif (hasattr(event, 'swing_high') and event.swing_high and 
                      hasattr(event, 'swing_low') and event.swing_low):
                    swing_start = event.time
                    swing_end = swing_start + pd.Timedelta(hours=2)  # Extend for visibility
                    fplt.add_rect((swing_start, event.swing_low), (swing_end, event.swing_high), 
                                color='lime', width_fill=0.2, ax=ax, text="SWING")
                
                # 3️⃣ Event marker (vertical line)
                else:
                    marker_time = event.time if hasattr(event, 'time') else df_5m.index[event.index]
                    fplt.plot(df_5m.index, df_5m['close'], ax=ax)  # Background
                    fplt.add_line((marker_time, df_5m['low'].min()), 
                                (marker_time, df_5m['high'].max()), 
                                color='orange', width=2, ax=ax)
                
                print(f"✅ Event {i+j}: {event_name}")
                
            except Exception as e:
                print(f"[plot_5m_legs] ❌ Event {i+j}: {e}")
        
        print(f"✅ Chunk {i+1}-{i+len(chunk)} plotted")
    
    fplt.show()

# Usage:
# plot_5m_legs(EVENTLOG or MASTERLOG, df_5m, chunk_size=3)
