"""Render-input types: the drawable view of the game the renderer consumes.

This is the neutral contract between the two sides that never import each other: the
*engine* produces a :class:`MovingPiece` for each in-flight piece
(``RealTimeArbiter.moving_pieces``), and the *view* — the local :mod:`graphics.renderer`
and the networked :mod:`client.snapshot_view` — draws from it. Keeping it here (rather
than inside ``engine.arbiter``) lets the view layer draw motion without reaching into
the engine, matching the architecture rule that the renderer owns no engine internals.

Unlike :mod:`kfchess.snapshot`, this is *not* a wire type: it holds a live
:class:`Piece` (so the renderer can pick its sprite) and model positions, so it does not
survive a JSON round-trip. The client rebuilds it each frame from a received snapshot.
It imports only the model, so it stays free of every layer above it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from kfchess.model.piece import Piece
from kfchess.model.position import Position


@dataclass(frozen=True)
class MovingPiece:
    """A read-only view of one in-flight piece: where it is now and its endpoints.

    Produced by ``RealTimeArbiter.moving_pieces`` for callers that render motion.
    ``position`` is a *fractional* cell — e.g. (3.5, 4.0) is halfway between two
    cells — not a board cell. It carries no way to mutate the underlying motion.
    """

    piece: Piece
    position: Tuple[float, float]
    source: Position
    target: Position
