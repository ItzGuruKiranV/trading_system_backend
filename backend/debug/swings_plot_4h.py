import plotly.graph_objects as go
import pandas as pd

def plot_swings_and_events_4h(df_4h, event_log, line_len_candles: int = 6):
    if df_4h.empty:
        raise ValueError("df_4h is empty")

    df = df_4h.copy()
    df.index = pd.to_datetime(df.index)
    df.reset_index(inplace=True)  # Plotly needs a column for x

    fig = go.Figure()

    # -------------------------
    # 1️⃣ Candles
    # -------------------------
    fig.add_trace(go.Candlestick(
        x=df['time'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name="4H Candles",
        increasing_line_color='green',
        decreasing_line_color='red',
        hovertemplate='Time: %{x}<br>O: %{open}<br>H: %{high}<br>L: %{low}<br>C: %{close}<extra></extra>'
    ))

    # -------------------------
    # 2️⃣ Events
    # -------------------------
    for e in event_log:
        if e.validation_tf != "4h":
            continue

        t_event = pd.to_datetime(e.time)
        if t_event not in df['time'].values:
            continue

        start_idx = df.index[df['time'] == t_event][0]
        end_idx = min(start_idx + line_len_candles, len(df) - 1)

        xmin = df.loc[start_idx, 'time']
        xmax = df.loc[end_idx, 'time']

        # Pullback Confirmed
        if e.event == "pullback_confirmed":
            price = df.loc[start_idx, 'close']
            fig.add_trace(go.Scatter(
                x=[t_event], y=[price],
                mode='markers',
                marker=dict(color='blue', size=10, symbol='circle'),
                name='Pullback Confirmed',
                hovertemplate=f'Time: {t_event}<br>Price: {price}<extra></extra>'
            ))

        # BOS / CHOCH horizontal lines
        elif e.event in ["bos_4h", "choch_4h"]:
            level = e.swing_high if e.swing_high is not None else e.swing_low
            if level is None:
                continue
            color = "black" if e.event=="bos_4h" else "yellow"
            name = "BOS (4H)" if e.event=="bos_4h" else "CHOCH (4H)"
            fig.add_trace(go.Scatter(
                x=[xmin, xmax],
                y=[level, level],
                mode='lines',
                line=dict(color=color, width=3),
                name=name,
                hovertemplate=f'Time Range: {xmin} - {xmax}<br>Level: {level}<extra></extra>'
            ))

        # POI rectangles or lines
        elif e.event == "poi_detected" and e.active_poi:
            poi = e.active_poi
            poi_type = poi.get("type")
            low = poi.get("price_low")
            high = poi.get("price_high")
            if low is None and high is None:
                continue

            color = "#C2185B" if poi_type=="LIQ" else "purple"
            name = "Liquidity POI" if poi_type=="LIQ" else "Order Block"

            if low is not None and high is not None:
                # rectangle as filled area
                fig.add_trace(go.Scatter(
                    x=[xmin, xmax, xmax, xmin, xmin],
                    y=[low, low, high, high, low],
                    fill='toself',
                    fillcolor=color,
                    line=dict(color=color),
                    opacity=0.25,
                    name=name,
                    hovertemplate=f'Time Range: {xmin} - {xmax}<br>Price Range: {low}-{high}<extra></extra>'
                ))
            else:
                price = low if low is not None else high
                fig.add_trace(go.Scatter(
                    x=[xmin, xmax],
                    y=[price, price],
                    mode='lines',
                    line=dict(color=color, width=3),
                    name=name,
                    hovertemplate=f'Time Range: {xmin} - {xmax}<br>Price: {price}<extra></extra>'
                ))

    fig.update_layout(
        title="4H Market Structure (Pullback → BOS → CHOCH → POI)",
        xaxis_title="Time",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        hovermode="x unified"
    )

    fig.write_html("debug_plot.html", auto_open=True)
