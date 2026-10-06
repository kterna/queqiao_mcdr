"""Exponential backoff reconnect calculator with jitter protection."""

import random
import time
from typing import Optional


class ReconnectBackoff:
    """Calculates progressive delay for reconnection attempts with optional randomization."""

    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        jitter_ratio: float = 0.1
    ):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter_ratio = jitter_ratio
        self._attempts = 0
        self._current_delay = initial_delay

    @property
    def attempts(self) -> int:
        return self._attempts

    def next_delay(self) -> float:
        self._attempts += 1
        base = min(self._current_delay, self.max_delay)

        # Apply jitter
        if self.jitter_ratio > 0:
            jitter = base * self.jitter_ratio * (random.random() * 2.0 - 1.0)
            actual = max(0.1, base + jitter)
        else:
            actual = base

        self._current_delay = min(self._current_delay * self.multiplier, self.max_delay)
        return round(actual, 3)

    def reset(self):
        self._attempts = 0
        self._current_delay = self.initial_delay
