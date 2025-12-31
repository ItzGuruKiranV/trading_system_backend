import matplotlib.pyplot as plt
import pandas as pd
from typing import Dict
from swings_plot import swing_state


# ======================================================
# 5M SWING + EVENT PLOT
# ======================================================
def plot_swings_and_events_5m(
    df_5m: pd.DataFrame,
    event_log
):
    if df_5m.empty:
        raise ValueError("df_5m is empty")

    df = df_5m.copy()

    # -------------------------
    # Ensure datetime index
    # -------------------------
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
        df.set_index("time", inplace=True)

    df.index = pd.to_datetime(df.index)

    fig, ax = plt.subplots(figsize=(20, 8))

    # ======================================================
    # Plot 5M Candles
    # ======================================================
    for idx, row in df.iterrows():
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        color = "green" if c >= o else "red"

        ax.plot([idx, idx], [l, h], color=color, linewidth=0.8)
        ax.plot([idx, idx], [o, c], color=color, linewidth=3)

    # ======================================================
    # Legend registry (avoid duplicates)
    # ======================================================
    legend_handles = {}

    def legend_once(label, artist):
        if label not in legend_handles:
            legend_handles[label] = artist

    # ======================================================
    # Plot EVENTS (5M only)
    # ======================================================
    for e in event_log:
        if e.validation_tf != "5m":
            continue

        t = pd.to_datetime(e.time)

        # --------------------------------------------------
        # POI TAPPED (small circle, OB / LIQ color)
        # --------------------------------------------------
        if e.event == "poi_tapped" and e.active_poi:
            poi_type = e.active_poi.get("type")

            price = (
                e.swing_high
                if e.swing_high is not None
                else e.swing_low
            )
            if price is None:
                continue

            color = "purple" if poi_type == "OB" else "#C2185B"

            sc = ax.scatter(
                t, price,
                s=20,
                color=color,
                zorder=7
            )
            legend_once("POI Tapped (OB / LIQ)", sc)

        # --------------------------------------------------
        # BOS WITHOUT POI (black circle)
        # --------------------------------------------------
        elif e.event == "bos_without_poi":
            price = e.swing_high if e.swing_high is not None else e.swing_low
            if price is None:
                continue

            sc = ax.scatter(
                t, price,
                s=20,
                color="black",
                zorder=8
            )
            legend_once("BOS (No POI)", sc)

        # --------------------------------------------------
        # M5 CHOCH (brown circle)
        # --------------------------------------------------
        elif e.event == "m5_choch":
            price = e.swing_high if e.swing_high is not None else e.swing_low
            if price is None:
                continue

            sc = ax.scatter(
                t, price,
                s=20,
                color="brown",
                zorder=8
            )
            legend_once("M5 CHOCH", sc)

        # --------------------------------------------------
        # CHOCH (light brown, smaller)
        # --------------------------------------------------
        elif e.event == "choch":
            price = e.swing_high if e.swing_high is not None else e.swing_low
            if price is None:
                continue

            sc = ax.scatter(
                t, price,
                s=20,
                color="#CD853F",  # light brown
                zorder=7
            )
            legend_once("CHOCH", sc)

        # --------------------------------------------------
        # RECENT SWING HIGH / LOW AFTER POI (magenta)
        # --------------------------------------------------
        elif e.event == "m5_structure_ready":
            price = e.swing_high if e.swing_high is not None else e.swing_low
            if price is None:
                continue

            sc = ax.scatter(
                t, price,
                s=20,
                color="magenta",
                zorder=7
            )
            legend_once("Post‑POI Swing High/Low", sc)

        # --------------------------------------------------
        # TRADE ENTRY / SL / TP (1:3 RR box)
        # --------------------------------------------------
        elif e.trade_details:
            td: Dict = e.trade_details

            entry = td.get("entry")
            sl = td.get("sl")
            tp = td.get("tp")

            if entry is None or sl is None or tp is None:
                continue

            width = pd.Timedelta(minutes=30)

            # SL box (red)
            sl_rect = plt.Rectangle(
                (t, min(entry, sl)),
                width,
                abs(entry - sl),
                color="red",
                alpha=0.25,
                zorder=3
            )
            ax.add_patch(sl_rect)
            legend_once("Stop Loss", sl_rect)

            # TP box (green)
            tp_rect = plt.Rectangle(
                (t, min(entry, tp)),
                width,
                abs(tp - entry),
                color="green",
                alpha=0.25,
                zorder=3
            )
            ax.add_patch(tp_rect)
            legend_once("Take Profit (1:3)", tp_rect)

            # Entry line
            ln = ax.hlines(
                y=entry,
                xmin=t,
                xmax=t + width,
                colors="blue",
                linewidth=2,
                zorder=4
            )
            legend_once("Entry", ln)

    # ======================================================
    # Styling
    # ======================================================
    ax.set_title("5M Execution Structure", fontsize=14)
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
