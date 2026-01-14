from typing import Dict
from engine1.state import PairState


class PairRegistry:
    def __init__(self):
        self.states: Dict[str, PairState] = {}

    def get(self, symbol: str) -> PairState:
        if symbol not in self.states:
            self.states[symbol] = PairState()
        return self.states[symbol]
