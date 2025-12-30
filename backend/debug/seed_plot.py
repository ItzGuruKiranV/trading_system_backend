"""
SEED PLOTTER - Fully Fixed Dynamic Real-Time Animation
"""
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import time
import pandas as pd
import numpy as np
from typing import List, Optional
from dataclasses import dataclass
from matplotlib.patches import Rectangle

@dataclass
class CandleState:
    index: int
    time: pd.Timestamp
    temp_trend: str
    pullback_active: bool
    protected_level: Optional[float] = None
    seed_high: float = 0.0
    seed_low: float = 0.0
    pullback_low: float = float('inf')
    pullback_high: float = float('-inf')
    event: Optional[str] = None
    pullback_start_idx: Optional[int] = None
    seed_complete: bool = False

class SeedPlotter:
    def __init__(self, df, states, wait=0.6):
        self.df = df
        self.states = states
        self.wait = wait
        print(f"🎬 SeedPlotter: {len(states)} frames @ {wait}s")
    
    def plot_candles(self, ax, ohlc_data):
        """Custom matplotlib candlesticks - FIXED mplfinance"""
        for i, (x, open_, high, low, close) in enumerate(ohlc_data):
            color = '#00ff88' if close >= open_ else '#ff4444'
            height = abs(close - open_)
            # Body
            rect = Rectangle((x-0.35, min(open_, close)), 0.7, height, 
                           facecolor=color, alpha=0.8, edgecolor='black', lw=1)
            ax.add_patch(rect)
            # Wicks
            ax.plot([x, x], [low, min(open_, close)], color='black', lw=1)
            ax.plot([x, x], [max(open_, close), high], color='black', lw=1)

    def initialize_plot(self):
        """Initialize figure and axis ONCE"""
        plt.ion()
        self.fig = plt.figure(figsize=(14, 9))
        self.ax = plt.subplot2grid((3, 3), (1, 0), colspan=3, rowspan=2)
        return self

    def plot_single_state(self, state):
        """🚀 DYNAMIC: Plot EXACTLY when change happens!"""
        if not hasattr(self, 'ax'):
            self.initialize_plot()
        
        self.ax.clear()
        
        # Candles up to current state
        candles = self.df.iloc[:state.index + 1]
        ohlc = [(i, candles.iloc[i]["open"], candles.iloc[i]["high"], 
                 candles.iloc[i]["low"], candles.iloc[i]["close"]) 
                for i in range(len(candles))]
        
        if len(ohlc):
            self.plot_candles(self.ax, ohlc)  # ✅ FIXED: Custom candles
        
        # SEED LINES (persistent)
        if state.seed_complete:
            self.ax.axhline(state.seed_high, color='lime', ls='--', lw=3, alpha=0.9, label='Seed High')
            self.ax.axhline(state.seed_low, color='red', ls='--', lw=3, alpha=0.9, label='Seed Low')
        
        # PROTECTED LEVEL
        if state.protected_level is not None:
            self.ax.axhline(state.protected_level, color='orange', ls='-', lw=3, label='Protected')
        
        # PULLBACK RANGE
        if state.pullback_low != float('inf') and state.pullback_high != float('-inf'):
            self.ax.axhspan(state.pullback_low, state.pullback_high, alpha=0.1, color='blue', label='Pullback Range')
        
        # ALL PAST EVENTS (persistent markers!)
        for past_idx, past_state in enumerate(self.states[:state.index + 1]):
            if past_state.event:
                colors = {
                    'PULLBACK_START': '#ffaa00', 
                    'PULLBACK_CONFIRMED': '#0066ff',
                    'PULLBACK_RESET': '#888888', 
                    'BOS': '#00ff00', 
                    'CHOCH': '#ff0000'
                }
                color = colors.get(past_state.event, '#ccc')
                size = 400 if past_state.event in ['BOS', 'CHOCH'] else 250
                past_close = candles.iloc[past_idx]["close"]
                self.ax.scatter(past_idx, past_close, c=color, s=size, marker='*',
                               zorder=10, ec='black', lw=2, alpha=0.9)
                self.ax.annotate(past_state.event, (past_idx, past_close),
                               xytext=(5, 20), textcoords='offset points',
                               fontsize=11, fontweight='bold', color=color)
        
        self.ax.grid(True, alpha=0.3)
        self.ax.legend(loc='upper left', fontsize=9)
        
        # DYNAMIC TITLE
        title = f"🔥 LIVE: {state.time.strftime('%H:%M')} | {state.temp_trend}"
        if state.event: 
            title += f" | ⭐ {state.event}"
        elif state.pullback_active: 
            title += " | 🔴 PULLBACK ACTIVE"
        else:
            title += f" | Candle #{state.index+1}"
        
        plt.title(title, fontsize=14, fontweight='bold', pad=20)
        plt.draw()
        plt.pause(0.3)  # Instant update!

    def animate(self):
        """Batch animation (not used in dynamic mode)"""
        self.initialize_plot()
        try:
            # EMPTY FRAME
            self.ax.clear()
            self.ax.text(0.5, 0.5, '🎬 WAITING...', ha='center', va='center', fontsize=24, color='white')
            self.ax.set_xlim(0, 10)
            self.ax.set_ylim(0, 1)
            plt.draw()
            plt.pause(1.5)
            
            # PERSISTENT ANIMATION (batch mode)
            for state in self.states:
                self.plot_single_state(state)  # Reuse dynamic method!
                
        except KeyboardInterrupt:
            print("⏹️ Stopped")
        finally:
            plt.ioff()
            plt.show(block=True)

def animate_seed_states(df, states):
    """Entry point - call from trend_seed (batch mode)"""
    plotter = SeedPlotter(df, states)
    plotter.animate()
