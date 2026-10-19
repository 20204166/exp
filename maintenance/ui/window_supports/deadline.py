"""Toolkit-neutral helpers for monotonic timer deadlines."""

from __future__ import annotations


def deadline_delay_ms(deadline: float, now: float) -> int:
    """Convert a monotonic deadline into a non-negative millisecond delay."""

    return max(0, int((deadline - now) * 1000))
