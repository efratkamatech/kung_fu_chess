"""Clock: the game's simulated time, in milliseconds.

A tiny piece of the engine layer. ``wait ms`` advances it; later iterations
(movement over time) compare a motion's arrival time against ``now_ms`` to decide
whether a moving piece has reached its destination yet. It knows nothing about the
board, pieces, or rules — just the current time.
"""

from __future__ import annotations


class Clock:
    """Holds the current simulated time. Starts at 0 and only moves forward."""

    __slots__ = ("_now_ms",)

    def __init__(self) -> None:
        self._now_ms = 0

    @property
    def now_ms(self) -> int:
        """The current simulated time in milliseconds."""
        return self._now_ms

    def advance(self, ms: int) -> None:
        """Move time forward by ``ms`` milliseconds."""
        if ms < 0:
            raise ValueError(f"cannot advance time by a negative amount: {ms}")
        self._now_ms += ms
