"""BusPublisher: bridge the engine's GameObserver callbacks onto the EventBus.

The core engine and arbiter announce game events through a small observer port
(``on_move_started`` / ``on_capture`` / ``on_game_over``) and know nothing about the
bus. This adapter *is* such an observer: every callback it receives, it re-publishes
as a typed bus event. Register one ``BusPublisher`` on the engine's observer list and
the whole application can then react through the single pub/sub hub — while the core
stays completely unaware the bus exists.
"""

from __future__ import annotations

from typing import Optional

from kfchess.bus.event_bus import EventBus
from kfchess.bus.events import Captured, CooldownDone, GameOver, MoveStarted, Settled
from kfchess.engine.events import GameObserver
from kfchess.model.color import Color
from kfchess.model.piece import Piece
from kfchess.model.position import Position


class BusPublisher(GameObserver):
    """A ``GameObserver`` that forwards every game event onto the ``EventBus``."""

    __slots__ = ("_bus",)

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def on_move_started(
        self,
        piece: Piece,
        source: Position,
        target: Position,
        start_ms: int,
        arrival_ms: int,
    ) -> None:
        self._bus.publish(MoveStarted(piece, source, target, start_ms, arrival_ms))

    def on_settled(
        self, piece: Piece, cell: Position, at_ms: int, cooldown_ms: int
    ) -> None:
        self._bus.publish(Settled(piece, cell, at_ms, cooldown_ms))

    def on_capture(self, victim: Piece, at_ms: int) -> None:
        self._bus.publish(Captured(victim, at_ms))

    def on_cooldown_done(self, piece: Piece, at_ms: int) -> None:
        self._bus.publish(CooldownDone(piece, at_ms))

    def on_game_over(self, winner: Optional[Color]) -> None:
        # The winner used to be dropped here: the only subscribers were sound and the
        # banner, which just need to know the game ended, and anyone who wanted the
        # winner read it off a snapshot. With no snapshot on every tick, the event has
        # to carry it -- it is the sole announcement the far side gets.
        self._bus.publish(GameOver(winner))
