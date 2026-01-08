import mplfinance as mpf
import pandas as pd
import matplotlib.pyplot as plt

def plot_5m_pois(all_legs_event_logs, df_5m):
    """
    Plots 5-minute POIs per leg using mplfinance.
    Uses leg_end snapshot only.
    """

    if not all_legs_event_logs:
        print("❌ No legs found")
        return

    for leg_idx, leg_events in enumerate(all_legs_event_logs, 1):

        # 🔹 Find leg_end snapshot
        leg_end_event = next(
            (e for e in leg_events if e.get("event") == "leg_end"),
            None
        )
        if not leg_end_event:
            continue

        leg_start = leg_end_event["start_time"]
        leg_end = leg_end_event["end_time"]

        df_leg = df_5m.loc[
            (df_5m.index >= leg_start) & 
            (df_5m.index <= leg_end)
        ]
        if df_leg.empty:
            continue

        # Plot candles
        fig, axlist = mpf.plot(
            df_leg,
            type='candle',
            style='charles',
            returnfig=True,
            volume=False,
            warn_too_much_data=10000,
            show_nontrading=True
        )
        ax = axlist[0]

        # -------------------------
        # Draw POIs (context only)
        # -------------------------
        for p in leg_end_event["pois"]:

            if p["type"] == "OB":
                ax.axhspan(
                    p["price_low"],
                    p["price_high"],
                    xmin=0,
                    xmax=1,
                    color='purple',
                    alpha=0.25
                )
                ax.hlines(p["price_high"], df_leg.index[0], df_leg.index[-1], colors='black', linewidth=1)
                ax.hlines(p["price_low"], df_leg.index[0], df_leg.index[-1], colors='brown', linewidth=1)

            elif p["type"] == "LIQ":
                price = p["price_low"] if p["price_low"] is not None else p["price_high"]
                ax.hlines(price, df_leg.index[0], df_leg.index[-1], colors='magenta', linewidth=1)

        # -------------------------
        # Mark tapped POI (if any)
        # -------------------------
        tapped_list = leg_end_event.get("tapped_pois", [])

        for tapped in tapped_list:
            tap_time = tapped["tap_time"]

            nearest_idx = df_leg.index.get_indexer([tap_time], method="nearest")[0]
            tap_ts = df_leg.index[nearest_idx]
            tap_candle = df_leg.loc[tap_ts]

            print(
                "TAP:", tap_time,
                "| LEG:", leg_start, "→", leg_end,
                "| INSIDE:", leg_start <= tap_time <= leg_end
            )

            ax.plot(
                tap_ts,
                tap_candle["close"],
                marker='*',
                color='black',
                markersize=14
            )

        # -------------------------
        # Mark protected 5M points (if any)
        # -------------------------
        protected_list = leg_end_event.get("protected_5m_points", [])

        for protected in protected_list:
            prot_time = protected["t"]
            prot_price = protected.get("price_low", protected.get("price_high"))

            # Snap to nearest candle for x-axis
            nearest_idx = df_leg.index.get_indexer([prot_time], method="nearest")[0]
            prot_ts = df_leg.index[nearest_idx]

            print(
                "PROTECTED 5M POINT:", prot_time,
                "| LEG:", leg_start, "→", leg_end,
                "| INSIDE:", leg_start <= prot_time <= leg_end,
                "| Y (price):", prot_price
            )

            # Plot at actual protected price, not candle high/low
            ax.plot(
                prot_ts,
                prot_price,
                marker='^',
                color='green',
                markersize=10
            )
        # -------------------------
        # Mark 5M structure events (CHOCH / BOS)
        # -------------------------
        structure_events = leg_end_event.get("choch_bos_events", [])

        for ev in structure_events:
            ev_time = ev["t"]
            ev_price = ev["price"]
            ev_type = ev["event"]

            # Snap to nearest candle for x-axis
            nearest_idx = df_leg.index.get_indexer([ev_time], method="nearest")[0]
            ev_ts = df_leg.index[nearest_idx]

            print(
                f"{ev_type} EVENT:", ev_time,
                "| LEG:", leg_start, "→", leg_end,
                "| INSIDE:", leg_start <= ev_time <= leg_end,
                "| Y (price):", ev_price
            )

            # Choose marker style by event type
            marker_style = "*" if ev_type == "CHOCH" else "v"  # CHOCH=star, BOS=down triangle
            color = "red" if ev_type == "CHOCH" else "blue"

            ax.plot(
                ev_ts,
                ev_price,
                marker=marker_style,
                color=color,
                markersize=12
            )
        # -------------------------
        # Draw 5M ORDER BLOCKS (light blue)
        # -------------------------
        obs = leg_end_event.get("five_m_obs", [])
        for ob in obs:
            ob_time = ob["ob_time"]
            ob_high = ob["ob_high"]
            ob_low = ob["ob_low"]

            # Snap to nearest candle
            nearest_idx = df_leg.index.get_indexer([ob_time], method="nearest")[0]
            ob_ts = df_leg.index[nearest_idx]

            # Small width (2 candles)
            width = 2
            start_idx = max(nearest_idx - width // 2, 0)
            end_idx = min(nearest_idx + width // 2, len(df_leg)-1)
            ob_start = df_leg.index[start_idx]
            ob_end = df_leg.index[end_idx]

            ax.axhspan(
                ob_low,
                ob_high,
                xmin=0, xmax=1,
                color="lightblue",
                alpha=0.25
            )
            # Optional thin border
            ax.hlines([ob_high, ob_low], ob_start, ob_end, colors='blue', linewidth=1)

        # -------------------------
        # Draw planned trade (1:3 R:R)
        # -------------------------
        trades = leg_end_event.get("planned_trade", [])
        for tr in trades:
            entry = tr["entry"]
            sl = tr["sl"]
            tp = tr["tp"]
            tr_time = tr.get("choch_time", leg_start)

            # Snap to nearest candle
            nearest_idx = df_leg.index.get_indexer([tr_time], method="nearest")[0]
            tr_ts = df_leg.index[nearest_idx]

            # Small width (2 candles)
            width = 2
            start_idx = max(nearest_idx - width // 2, 0)
            end_idx = min(nearest_idx + width // 2, len(df_leg)-1)
            tr_start = df_leg.index[start_idx]
            tr_end = df_leg.index[end_idx]

            # Black box = entry → SL
            ax.axhspan(
                min(entry, sl),
                max(entry, sl),
                xmin=0, xmax=1,
                color="black",
                alpha=0.3
            )
            # Grey box = entry → TP
            ax.axhspan(
                min(entry, tp),
                max(entry, tp),
                xmin=0, xmax=1,
                color="grey",
                alpha=0.3
            )



        # ✅ Display the figure for this leg
        ax.set_title(f"5M Structural Leg {leg_idx}")
        fig.tight_layout()
        plt.show()

    print(f"✅ Plotted {len(all_legs_event_logs)} structural legs")
