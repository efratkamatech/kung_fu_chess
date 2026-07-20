"""GameBanner: track which start/end overlay to show, driven by bus events.

A pure state-holder subscriber: it listens on the bus and remembers the current game
*phase*, so the frame loop knows which overlay to draw. The start overlay shows from
the moment a game begins until the first move is made; the game-over overlay shows once
a king falls. There are no timers — the phase advances purely on events
(``GAME_STARTED`` -> ``MOVE_STARTED`` -> ``GAME_OVER``), which keeps it fully testable.
"""

from __future__ import annotations

from kfchess.bus import topics
from kfchess.bus.event_bus import EventBus

# The three phases a game moves through, as far as the overlays are concerned.
START = "start"      # a new game has begun; show the start overlay
PLAYING = "playing"  # the first move has been made; no overlay
OVER = "over"        # a king was captured; show the game-over overlay


class GameBanner:
    """Remembers the current game phase from bus events; read by the frame loop."""

    __slots__ = ("_phase",)

    def __init__(self) -> None:
        self._phase = PLAYING  # neutral until a GAME_STARTED event arrives

    def subscribe(self, bus: EventBus) -> None:
        """Advance the phase on game start, the first move, and game over."""
        bus.subscribe(topics.GAME_STARTED, self._on_start)
        bus.subscribe(topics.MOVE_STARTED, self._on_move)
        bus.subscribe(topics.GAME_OVER, self._on_over)

    def _on_start(self, event) -> None:
        self._phase = START

    def _on_move(self, event) -> None:
        if self._phase == START:  # the first move dismisses the start overlay
            self._phase = PLAYING

    def _on_over(self, event) -> None:
        self._phase = OVER

    @property
    def show_start(self) -> bool:
        """True while the start overlay should be shown."""
        return self._phase == START

    @property
    def is_over(self) -> bool:
        """True once the game-over overlay should be shown."""
        return self._phase == OVER
