from candle_stream import Candle
from state import PairState

class PairEngine:
    def __init__(self, state: PairState):
        self.state = state
        self._buffer_4h = []

    def on_candle(self, candle: Candle):
        # Build 4H candle from 1M
        self._buffer_4h.append(candle)

        if len(self._buffer_4h) == 240:
            self.process_4h_candle(self._buffer_4h)
            self._buffer_4h.clear()

    def process_4h_candle(self, candles_4h):
        s = self.state

        high = max(c.high for c in candles_4h)
        low = min(c.low for c in candles_4h)
        close = candles_4h[-1].close
        time = candles_4h[-1].time

        # INITIAL SEED
        if s.last_swing_high is None:
            s.last_swing_high = high
            s.last_swing_low = low
            return

        # BOS LOGIC
        if s.trend_4h != "BULLISH" and close > s.last_swing_high:
            s.trend_4h = "BULLISH"
            s.bos_time_4h = time
            s.protected_low = s.last_swing_low
            s.phase = "PULLBACK"
            self.emit("BOS_4H", time)

        elif s.trend_4h != "BEARISH" and close < s.last_swing_low:
            s.trend_4h = "BEARISH"
            s.bos_time_4h = time
            s.protected_high = s.last_swing_high
            s.phase = "PULLBACK"
            self.emit("BOS_4H", time)

        # UPDATE SWINGS
        s.last_swing_high = max(s.last_swing_high, high)
        s.last_swing_low = min(s.last_swing_low, low)

        # PULLBACK CHECK
        if s.phase == "PULLBACK":
            self.check_pullback(high, low, close, time)

    def check_pullback(self, high, low, close, time):
        s = self.state

        if s.trend_4h == "BULLISH":
            if s.candidate_high is None or high > s.candidate_high:
                s.candidate_high = high
                s.bearish_count = 0
                return

            if close < s.candidate_high:
                s.bearish_count += 1

            if s.bearish_count >= 3:
                s.pullback_confirmed = True
                s.phase = "READY"
                self.emit("PULLBACK_CONFIRMED", time)

        if s.trend_4h == "BEARISH":
            if s.candidate_low is None or low < s.candidate_low:
                s.candidate_low = low
                s.bullish_count = 0
                return

            if close > s.candidate_low:
                s.bullish_count += 1

            if s.bullish_count >= 3:
                s.pullback_confirmed = True
                s.phase = "READY"
                self.emit("PULLBACK_CONFIRMED", time)

    def emit(self, event, time):
        self.state.events.append({
            "symbol": self.state.symbol,
            "event": event,
            "time": time
        })
