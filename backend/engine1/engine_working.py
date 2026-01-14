import pandas as pd
from engine1.state import PairState
from engine.swings_detect import market_structure_mapping


class PairEngine:
    def __init__(self, symbol: str, state: PairState):
        self.symbol = symbol
        self.state = state

        self.df_4h = pd.DataFrame(columns=["open","high","low","close"])
        self.df_5m = pd.DataFrame(columns=["open","high","low","close"])

        self.last_processed_4h = None

        # capture events
        self._events = []

    # --------------------------------------------------
    # EVENT HOOK (THIS IS THE KEY)
    # --------------------------------------------------
    def log_event_master(self, **kwargs):
        self._events.append(kwargs)

    # --------------------------------------------------
    def on_new_4h_candle(self, time, o, h, l, c):
        self.df_4h.loc[time] = [o, h, l, c]

        # call YOUR logic
        self.run_structure()

        # process captured events
        self.flush_events()

    # --------------------------------------------------
    def run_structure(self):
        self._events.clear()

        market_structure_mapping(
            df_4h=self.df_4h.copy(),
            df_5m=self.df_5m.copy(),
            trend=self.state.trend or "BULLISH",
            bos_time=self.state.bos_time,
        )

    # --------------------------------------------------
    def flush_events(self):
        for e in self._events:
            event = e.get("event")

            if event == "bos_4h":
                self.state.trend = e["trend"]
                self.state.bos_price = e.get("swing_high") or e.get("swing_low")
                self.state.bos_time = e["time"]

            elif event == "choch_4h":
                self.state.trend = e["trend"]
                self.state.choch_price = e.get("swing_low") or e.get("swing_high")
                self.state.choch_time = e["time"]

            elif event == "pullback_confirmed":
                self.state.pullback_price = e.get("swing_low") or e.get("swing_high")
                self.state.pullback_time = e["time"]
                self.state.pullback_candle_count = e.get("candle_count", 0)
