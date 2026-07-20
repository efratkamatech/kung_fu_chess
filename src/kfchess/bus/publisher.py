"""BusPublisher: bridge the engine's GameObserver callbacks onto the EventBus.

The core engine and arbiter announce game events through a small observer port
(``on_move_started`` / ``on_capture`` / ``on_game_over``) and know nothing about the
bus. This adapter *is* such an observer: every callback it receives, it re-publishes
as a typed bus event. Register one ``BusPublisher`` on the engine's observer list and
the whole application can then react through the single pub/sub hub — while the core
stays completely unaware the bus exists.
"""

from __future__ import annotations

from kfchess.bus.event_bus import EventBus
from kfchess.bus.events import Captured, GameOver, MoveStarted
from kfchess.engine.events import GameObserver
from kfchess.model.piece import Piece
from kfchess.model.position import Position


class BusPublisher(GameObserver):
    """A ``GameObserver`` that forwards every game event onto the ``EventBus``."""

    __slots__ = ("_bus",)

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def on_move_started(
        self, piece: Piece, source: Position, target: Position
    ) -> None:
        self._bus.publish(MoveStarted(piece, source, target))

    def on_capture(self, victim: Piece) -> None:
        self._bus.publish(Captured(victim))

    def on_game_over(self) -> None:
        # No current subscriber needs the winner (sound/animation only need to know the
        # game ended), so GameOver.winner stays None for now. When a subscriber that
        # needs it appears (ELO rating in M4), it is populated here.
        self._bus.publish(GameOver())
