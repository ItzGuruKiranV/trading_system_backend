# debug/plot_5m.py
import finplot as fplt
import pandas as pd

def plot_5m_legs(all_legs_event_logs, df_5m, chunk_size=5):
    """
    Plots 5M legs with rectangles for each swing leg.
    all_legs_event_logs: List of dicts with keys ['start', 'end', 'low', 'high', 'type']
    df_5m: 5M dataframe with datetime index
    chunk_size: how many legs per plot (to avoid overcrowding)
    """
    if not all_legs_event_logs:
        print("[plot_5m_legs] ⚠️ No leg events to plot")
        return

    # Ensure df_5m index is datetime and sorted
    df_5m = df_5m.copy()
    df_5m.sort_index(inplace=True)
    if not isinstance(df_5m.index, pd.DatetimeIndex):
        df_5m.index = pd.to_datetime(df_5m.index)

    # Split events into chunks
    for i in range(0, len(all_legs_event_logs), chunk_size):
        chunk = all_legs_event_logs[i:i + chunk_size]
        start_idx = chunk[0]['start']
        end_idx = chunk[-1]['end']

        # Try to map to actual timestamps in df_5m
        try:
            if isinstance(start_idx, int):
                start_5m_time = df_5m.index[start_idx]  # fallback if index is integer
            else:
                start_5m_time = start_idx
            if isinstance(end_idx, int):
                end_5m_time = df_5m.index[end_idx]
            else:
                end_5m_time = end_idx
        except Exception:
            print(f"[plot_5m_legs] ⚠️ Could not map leg indices to timestamps, skipping chunk {i}-{i+chunk_size}")
            continue

        # Create a new plot for each chunk
        ax, _ = fplt.create_plot(f"5M Swings {i+1}-{i+len(chunk)}", init_zoom_periods=100)
        fplt.candlestick_ochl(df_5m[['open','close','high','low']], ax=ax)

        # Draw rectangles
        for leg in chunk:
            try:
                low = leg.get('low')
                high = leg.get('high')
                leg_type = leg.get('type', 'LEG')
                start_time = leg.get('start')
                end_time = leg.get('end')

                # Map start/end to actual timestamps in df_5m
                if isinstance(start_time, int):
                    start_time = df_5m.index[start_time]
                if isinstance(end_time, int):
                    end_time = df_5m.index[end_time]

                # Skip if low/high or timestamps missing
                if low is None or high is None or start_time is None or end_time is None:
                    print(f"[plot_5m_legs] ⚠️ Skipping leg due to missing data: {leg}")
                    continue

                # Choose color
                color = 'green' if leg_type.upper() == 'BULL' else 'red'

                fplt.add_rect(
                    (start_time, low),
                    (end_time, high),
                    color=color,
                    ax=ax,
                    text=leg_type
                )
            except Exception as e:
                print(f"[plot_5m_legs] ❌ Error plotting leg: {leg}")
                print(e)

        fplt.show()
