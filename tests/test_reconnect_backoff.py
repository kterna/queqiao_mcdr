"""Unit tests for ReconnectBackoff."""

import pytest
from queqiao_mcdr.reconnect_backoff import ReconnectBackoff


def test_reconnect_backoff_progression():
    backoff = ReconnectBackoff(initial_delay=1.0, max_delay=8.0, multiplier=2.0, jitter_ratio=0.0)

    # First attempt: 1.0
    assert backoff.next_delay() == 1.0
    assert backoff.attempts == 1

    # Second: 2.0
    assert backoff.next_delay() == 2.0

    # Third: 4.0
    assert backoff.next_delay() == 4.0

    # Fourth: 8.0 (capped at max)
    assert backoff.next_delay() == 8.0

    # Fifth: still 8.0
    assert backoff.next_delay() == 8.0

    # Reset
    backoff.reset()
    assert backoff.attempts == 0
    assert backoff.next_delay() == 1.0


def test_reconnect_backoff_jitter():
    backoff = ReconnectBackoff(initial_delay=10.0, max_delay=10.0, jitter_ratio=0.1)
    d = backoff.next_delay()
    # Should be between 9.0 and 11.0
    assert 8.9 <= d <= 11.1
