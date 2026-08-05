"""RuleEngine: read-only legality of a requested move.

Given the board and a move (source -> target), decide whether it is legal. It is
strictly read-only: it never mutates the board (that is the GameEngine's job). The
movement rules are injected, so the set of pieces/geometry is configurable.

It checks shape legality (the piece's geometry reaches the target, with the path
clear — the path check lives in SlideMovement), the capture rule (you cannot land
on your own color; an enemy at the destination is a legal capture), and that the
piece is free to act — neither in flight (a moving piece cannot be redirected) nor
on cooldown from a recent landing.
"""

from __future__ import annotations

from typing import List

from kfchess.model.board import Board
from kfchess.model.piece import PieceState
from kfchess.model.position import Position
from kfchess.movement.rules import MovementRuleSet


class RuleEngine:
    """Answers whether a requested move is legal. Never changes the board."""

    def __init__(self, movement_rules: MovementRuleSet) -> None:
        self._movement_rules = movement_rules

    def is_legal_move(
        self, board: Board, source: Position, target: Position
    ) -> bool:
        piece = board.piece_at(source)
        if piece is None:
            return False  # nothing to move

        if piece.state in (PieceState.MOVING, PieceState.COOLDOWN):
            return False  # in flight (can't redirect) or cooling down after a landing

        letter = piece.piece_type.letter
        if letter not in self._movement_rules:
            return False  # a piece with no movement rule can't move (e.g. pawn pre-iter5)

        if not self._movement_rules.get(letter).can_reach(
            piece, source, target, board
        ):
            return False

        # Capture rule: an empty destination is a plain move, an enemy there is a
        # legal capture, but you cannot land on a piece of your own color.
        occupant = board.piece_at(target)
        if occupant is not None and occupant.color == piece.color:
            return False
        return True


def legal_targets(
    rule_engine: RuleEngine, board: Board, source: Position
) -> List[Position]:
    """Every cell the piece at ``source`` may legally move to on ``board`` right now.

    A rendering aid — the green hints drawn under a selected piece — and deliberately
    the *only* place that answers it. The windowed game holds a live engine and the
    networked client holds a board rebuilt from snapshots, but both highlight through
    here, so what a player is shown as reachable is decided by the same rule that will
    judge the move when she makes it.

    Empty if the cell holds no piece or the piece cannot move (mid-flight, or cooling
    down after a landing).
    """
    return [
        Position(row, col)
        for row in range(board.rows)
        for col in range(board.cols)
        if rule_engine.is_legal_move(board, source, Position(row, col))
    ]
