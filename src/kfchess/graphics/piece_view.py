"""PieceView: the animation state machine — maps a piece's core state to its sprites.

The game core already tracks each piece's lifecycle state (``IDLE``, ``MOVING``,
``JUMPING``, ``COOLDOWN``). PieceView is the bridge to the visuals: it translates that
state to the matching sprite-folder name and, crucially, remembers *when* the piece
entered its current state so the animation can play from its first frame on every
transition (e.g. the moment a piece starts moving, its ``move`` animation restarts).

It holds per-piece timing that must persist across frames, so a single PieceView lives
for the whole game (owned by the renderer) rather than being rebuilt each frame.
"""

from __future__ import annotations

from typing import Dict, Tuple

from kfchess.config import STATE_IDLE, STATE_JUMP, STATE_LONG_REST, STATE_MOVE
from kfchess.model.piece import Piece, PieceState

# Which sprite-folder animation to play for each core lifecycle state. A piece just
# off a move is on COOLDOWN, shown with the long-rest animation (the assets' own
# ``move -> long_rest`` follow-up).
_ANIMATION_STATE: Dict[PieceState, str] = {
    PieceState.IDLE: STATE_IDLE,
    PieceState.MOVING: STATE_MOVE,
    PieceState.JUMPING: STATE_JUMP,
    PieceState.COOLDOWN: STATE_LONG_REST,
}


class PieceView:
    """Per-piece animation-state tracker: current state name plus time since entering it."""

    __slots__ = ("_entered",)

    def __init__(self) -> None:
        # piece -> (core state it is in, game-time ms when it entered that state)
        self._entered: Dict[Piece, Tuple[PieceState, int]] = {}

    def state_and_elapsed(self, piece: Piece, now_ms: int) -> Tuple[str, int]:
        """Return ``(animation_state_name, ms_since_entering_it)`` for ``piece``.

        When the piece's core state differs from what we last recorded, its entry time
        resets to ``now_ms`` so the new animation starts from frame 0.
        """
        core_state = piece.state
        previous = self._entered.get(piece)
        if previous is None or previous[0] is not core_state:
            self._entered[piece] = (core_state, now_ms)
            entered_ms = now_ms
        else:
            entered_ms = previous[1]
        return _ANIMATION_STATE[core_state], now_ms - entered_ms
