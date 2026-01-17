from backend.engine1.state import PairState

class StateRegistry:
    def __init__(self):
        self._states = {}

    def get_state(self, symbol: str) -> PairState:
        if symbol not in self._states:
            self._states[symbol] = PairState(symbol=symbol)
        return self._states[symbol]
