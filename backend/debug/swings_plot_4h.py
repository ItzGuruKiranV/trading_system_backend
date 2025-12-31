import matplotlib.pyplot as plt
import pandas as pd
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from swings_plot import swing_state
# =========================
# Plot Function
# =========================
def plot_swings_and_events_4h(
    df_4h: pd.DataFrame,
    event_log
):
    if df_4h.empty:
        raise ValueError("df_4h is empty")

    df = df_4h.copy()

    # Ensure datetime index
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
        df.set_index("time", inplace=True)

    df.index = pd.to_datetime(df.index)

    fig, ax = plt.subplots(figsize=(18, 8))

    # =========================
    # Plot 4H Candles
    # =========================
    for idx, row in df.iterrows():
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        color = "green" if c >= o else "red"

        ax.plot([idx, idx], [l, h], color=color, linewidth=1)
        ax.plot([idx, idx], [o, c], color=color, linewidth=4)

    # =========================
    # Legend registry
    # =========================
    legend_handles = {}

    def legend_once(label, artist):
        if label not in legend_handles:
            legend_handles[label] = artist

    # =========================
    # Distance rule
    # =========================
    MAX_DISTANCE = pd.Timedelta(hours=2)

    # =========================
    # Plot EVENTS (4H only)
    # =========================
    for e in event_log:
        if e.validation_tf != "4h":
            continue

        t_event = pd.to_datetime(e.time)

        if e.event == "start":
            # ---------- EXACT MATCH ----------
            if t_event in df.index:
                price = df.loc[t_event]["close"]
                sc = ax.scatter(
                    t_event, price,
                    s=40,
                    color="#B8860B",  # dark yellow
                    zorder=6
                )
                legend_once("Structure Start BOS (Exact)", sc)

            # ---------- NEARBY MATCH ----------
            else:
                nearest_idx = df.index.get_indexer(
                    [t_event], method="nearest"
                )[0]
                nearest_time = df.index[nearest_idx]
                delta = abs(nearest_time - t_event)

                if delta <= MAX_DISTANCE:
                    price = df.loc[nearest_time]["close"]
                    sc = ax.scatter(
                        nearest_time, price,
                        s=40,
                        color="yellow",
                        zorder=5
                    )
                    legend_once("Structure Start BOS (Nearby ≤2h)", sc)
                # else: intentionally NOT plotted
        elif e.event == "pullback_confirmed":

            if e.swing_low is not None:
                price = e.swing_low
            elif e.swing_high is not None:
                price = e.swing_high
            else:
                continue  # safety

            sc = ax.scatter(
                t_event, price,
                marker="*",
                s=120,
                color="blue",
                zorder=7
            )
            legend_once("Pullback Confirmed", sc)
        elif e.event == "bos_without_poi":
            # -----------------------------
            # BOS price (from swing)
            # -----------------------------
            price = e.swing_high if e.swing_high is not None else e.swing_low
            if price is None:
                continue  # safety

            sc = ax.scatter(
                t_event,
                price,
                s=50,
                color="black",
                zorder=8
            )
            legend_once("BOS Continuation", sc)

        elif e.event == "poi_detected" and e.active_poi:
            poi = e.active_poi
            poi_type = poi.get("type")  # "LIQ" or "OB"

            low = poi.get("price_low")
            high = poi.get("price_high")

            # -----------------------------
            # Safety: nothing to plot
            # -----------------------------
            if low is None and high is None:
                continue

            # -----------------------------
            # Time width (local visibility)
            # -----------------------------
            width = pd.Timedelta(hours=12)  # 3 x 4H candles

            # -----------------------------
            # STYLE BY TYPE
            # -----------------------------
            if poi_type == "LIQ":
                color = "#C2185B"   # pink
                label_range = "Liquidity POI (Range)"
                label_line = "Liquidity POI (Single Price)"

            elif poi_type == "OB":
                color = "purple"
                label_range = "Order Block (Range)"
                label_line = "Order Block (Single Price)"

            else:
                continue  # unknown POI type

            # -----------------------------
            # CASE 1: FULL RANGE → RECTANGLE
            # -----------------------------
            if low is not None and high is not None:
                rect = plt.Rectangle(
                    (t_event, low),
                    width,
                    high - low,
                    color=color,
                    alpha=0.3,
                    zorder=4
                )
                ax.add_patch(rect)
                legend_once(label_range, rect)

            # -----------------------------
            # CASE 2: PARTIAL → HORIZONTAL LINE
            # -----------------------------
            else:
                price = low if low is not None else high
                ln = ax.hlines(
                    y=price,
                    xmin=t_event,
                    xmax=t_event + width,
                    colors=color,
                    linewidth=2,
                    zorder=5
                )
                legend_once(label_line, ln)



    # =========================
    # Styling
    # =========================
    ax.set_title("4H Market Structure (Debug View)", fontsize=14)
    ax.set_xlabel("Time")
    ax.set_ylabel("Price")
    ax.grid(alpha=0.2)

    if legend_handles:
        ax.legend(
            legend_handles.values(),
            legend_handles.keys(),
            loc="upper left",
            fontsize=9
        )
    
    fig.autofmt_xdate()
    plt.tight_layout()
    plt.show()
