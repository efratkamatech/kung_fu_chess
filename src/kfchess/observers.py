"""Game-state observers: the scoreboard, the moves log, and the start/end banner.

These three subscribe to the :class:`EventBus` and accumulate *state* from game events
— they hold no drawing code and no game rules, only what happened. The architecture
models them as their own layers (ScoreKeeper, MoveHistory, and a display-phase tracker),
independent of any UI, so they live here at the package root rather than under
``graphics``: the windowed client draws from them, and the headless server reads them to
build a snapshot — neither pulls in the other's dependencies.
"""

from __future__ import annotations

from typing import Dict, List

from kfchess.algebraic import position_to_square
from kfchess.bus import topics
from kfchess.bus.event_bus import EventBus
from kfchess.model.color import Color
from kfchess.tokens import piece_token

# The three phases a game moves through, as far as the start/end banner is concerned.
START = "start"      # a new game has begun; show the start overlay
PLAYING = "playing"  # the first move has been made; no overlay
OVER = "over"        # a king was captured; show the game-over overlay


class MovesLog:
    """Records a human-readable line per move/capture, kept separately per side.

    A move is logged to the mover's side; a capture is logged to the *captor's* side
    (the victim's opponent), so each player's panel shows their own moves and kills.
    """

    def __init__(self, board_rows: int) -> None:
        # Board height, so a row index becomes a chess-style rank (bottom row = 1).
        self._board_rows = board_rows
        self._by_color: Dict[Color, List[str]] = {Color.WHITE: [], Color.BLACK: []}

    def subscribe(self, bus: EventBus) -> None:
        """Listen for move-starts and captures on ``bus``."""
        bus.subscribe(topics.MOVE_STARTED, self._on_move)
        bus.subscribe(topics.CAPTURE, self._on_capture)

    def _on_move(self, event) -> None:
        source = position_to_square(event.source, self._board_rows)
        target = position_to_square(event.target, self._board_rows)
        self._by_color[event.piece.color].append(
            f"{piece_token(event.piece)} {source} -> {target}"
        )

    def _on_capture(self, event) -> None:
        self._by_color[event.victim.color.opponent].append(
            f"x {piece_token(event.victim)}"
        )

    def recent(self, color: Color, count: int) -> List[str]:
        """The most recent ``count`` log lines for ``color`` (oldest first)."""
        return self._by_color[color][-count:]


class ScoreBoard:
    """Tallies, per side, the total material value captured by that side."""

    def __init__(self) -> None:
        self._score: Dict[Color, int] = {Color.WHITE: 0, Color.BLACK: 0}

    def subscribe(self, bus: EventBus) -> None:
        """Listen for captures on ``bus``."""
        bus.subscribe(topics.CAPTURE, self._on_capture)

    def _on_capture(self, event) -> None:
        # A capture is always by the enemy, so the victim's opponent earns its value.
        self._score[event.victim.color.opponent] += event.victim.piece_type.cost

    def score(self, color: Color) -> int:
        """The total captured value credited to ``color``."""
        return self._score[color]


class GameBanner:
    """Tracks the game phase (start -> playing -> over) from bus events.

    The start phase holds from a new game until the first move dismisses it; the over
    phase begins when a king falls. Purely event-driven, no timers — so the frame loop
    (and the snapshot) can just read the current phase.
    """

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
    def phase(self) -> str:
        """The current phase: ``"start"``, ``"playing"``, or ``"over"``."""
        return self._phase

    @property
    def show_start(self) -> bool:
        """True while the start overlay should be shown."""
        return self._phase == START

    @property
    def is_over(self) -> bool:
        """True once the game-over overlay should be shown."""
        return self._phase == OVER
