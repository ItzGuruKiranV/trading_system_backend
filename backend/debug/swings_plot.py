"""
SWINGS PLOTTER — TRUE REAL-TIME INCREMENTAL (4H ONLY)
✔ Candles drawn ONCE
✔ No backward time
✔ No candle loss
✔ Marker-only structure (^ v)
✔ No ax.clear()
✔ No slicing
✔ Plot stays forever
"""

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import pandas as pd
from dataclasses import dataclass
from typing import Optional, Dict, Tuple

# =========================
# STATE OBJECT
# =========================

@dataclass
class swing_state:
    index: int
    time: pd.Timestamp
    trend: str
    event: Optional[str] = None
    swing_high: Optional[float] = None
    swing_low: Optional[float] = None
    active_poi: Optional[Dict] = None
    trade_details: Optional[Dict] = None
    rr_ratio: Optional[float] = None
    liquidity_grabbed: bool = False

# =========================
# PLOTTER
# =========================

class swings_plotter:
    def __init__(self, df_4h: pd.DataFrame):
        self.df_4h = df_4h.reset_index(drop=True)
        self.fig = None
        self.ax = None
        self.initialized = False
        self.last_drawn_index = -1
        self.drawn_pois = set()

    # -------------------------
    def initialize_plot(self):
        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=(18, 9))
        self.ax.set_title("4H Market Structure (LIVE)")
        self.ax.set_xlabel("Candle Index")
        self.ax.set_ylabel("Price")
        self.ax.grid(True, alpha=0.3)
        self.initialized = True

    # -------------------------
    def draw_candle(self, x: int, row: pd.Series):
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        color = "#00ff88" if c >= o else "#ff4444"
        
        # Wick
        self.ax.plot([x, x], [l, h], color=color, lw=1, zorder=1)
        
        # Body
        body = Rectangle(
            xy=(x - 0.3, min(o, c)),
            width=0.6,
            height=abs(c - o),
            facecolor=color,
            edgecolor=color,
            zorder=2
        )
        self.ax.add_patch(body)

    # -------------------------
    def draw_event(self, x: int, y: float, label: str):
        self.ax.scatter(
            x, y,
            s=300,
            marker="^",
            c="yellow",
            edgecolors="black",
            zorder=10
        )
        self.ax.text(
            x, y,
            f" {label}",
            fontsize=9,
            color="yellow",
            va="bottom",
            zorder=11
        )

    # -------------------------
    def draw_poi(self, poi):
        # Handle both dict and swing_state
        if isinstance(poi, dict):
            low = poi.get('price_low') or poi.get('low')
            high = poi.get('price_high') or poi.get('high')
        else:  # swing_state or other object
            low = getattr(poi, 'price_low', None) or getattr(poi, 'low', None)
            high = getattr(poi, 'price_high', None) or getattr(poi, 'high', None)
        
        if low is not None and high is not None:
            self.ax.axhspan(low, high, color='#ffaa00', alpha=0.25, zorder=0)


    # -------------------------
    def plot_single_state(self, state: swing_state, **kwargs):
        if not self.initialized:
            self.initialize_plot()
        
        idx = int(state.index)
        if idx < 0 or idx >= len(self.df_4h):
            return
        
        # 1️⃣ Draw candles ONCE
        while self.last_drawn_index < idx:
            self.last_drawn_index += 1
            row = self.df_4h.iloc[self.last_drawn_index]
            self.draw_candle(self.last_drawn_index, row)
        
        row = self.df_4h.iloc[idx]
        
        # 2️⃣ Structure markers
        if state.swing_high is not None:
            self.ax.scatter(
                idx, state.swing_high,
                marker="^",
                s=260,
                c="lime",
                edgecolors="black",
                zorder=8
            )
        if state.swing_low is not None:
            self.ax.scatter(
                idx, state.swing_low,
                marker="v",
                s=260,
                c="red",
                edgecolors="black",
                zorder=8
            )
        
        # 3️⃣ POI (draw once) - support extra dict
        poi_info = kwargs.get("extra", {}).get("active_poi", state.active_poi)
        if poi_info:
            poi_low = poi_info.get("price_low")
            poi_high = poi_info.get("price_high")
            if poi_low is not None and poi_high is not None:
                poi_id = (poi_low, poi_high)
                if poi_id not in self.drawn_pois:
                    self.draw_poi(poi_info)
                    self.drawn_pois.add(poi_id)
        
        # 4️⃣ Event marker
        if state.event:
            y = row["close"]
            label = state.event.upper()
            if state.event in ["trade_entry", "trade_rejected_tp_high", "trade_rejected_tp_low",
                               "tp_hit", "sl_hit", "entry_filled"]:
                self.ax.scatter(idx, y, s=300, marker="*", c="cyan", edgecolors="black", zorder=12)
                self.ax.text(idx, y, f" {label}", fontsize=9, color="cyan", va="bottom", zorder=13)
            else:
                self.draw_event(idx, y, label)
        
        # 5️⃣ X-axis camera ONLY
        self.ax.set_xlim(max(0, idx - 120), idx + 10)
        
        # ✅ Let Y-axis autoscale naturally
        self.ax.relim()
        self.ax.autoscale_view(scalex=False, scaley=True)
        
        # 6️⃣ Title
        self.fig.suptitle(
            f"4H LIVE | {state.time} | Trend: {state.trend} | Index: {idx}",
            fontsize=14
        )
        
        # 7️⃣ Flush
        plt.draw()
        plt.pause(0.8)  # speed control
