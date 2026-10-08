"""Validated exponential reconnect delay with a strict post-jitter cap."""
import math
import random
from typing import Callable, Optional


def finite_number(value, name, minimum, maximum):
    """Reject bool, nonnumeric and nonfinite configuration before mutating state."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"{name} is outside its supported range")
    return result


class ReconnectBackoff:
    """One client owns this policy; successful stable sessions reset its attempts."""

    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        jitter_ratio: float = 0.1,
        random_fn: Optional[Callable[[], float]] = None,
    ):
        self.initial_delay = finite_number(initial_delay, "initial_delay", 0.001, 3600)
        self.max_delay = finite_number(max_delay, "max_delay", self.initial_delay, 3600)
        self.multiplier = finite_number(multiplier, "multiplier", 1, 100)
        self.jitter_ratio = finite_number(jitter_ratio, "jitter_ratio", 0, 0.5)
        self._random = random_fn or random.random
        self.reset()

    @property
    def attempts(self) -> int:
        return self._attempts

    def next_delay(self) -> float:
        base = self._current_delay
        jitter = 0.0
        if self.jitter_ratio:
            sample = finite_number(self._random(), "random sample", 0, 1)
            jitter = base * self.jitter_ratio * (sample * 2 - 1)
        delay = min(self.max_delay, max(0.001, base + jitter))
        self._attempts += 1
        self._current_delay = min(self.max_delay, base * self.multiplier)
        return delay

    def reset(self):
        self._attempts = 0
        self._current_delay = self.initial_delay
