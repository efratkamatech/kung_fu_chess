"""RuleEngine: read-only legality of a requested move.

Given the board and a move (source -> target), decide whether it is legal. It is
strictly read-only: it never mutates the board (that is the GameEngine's job). The
movement rules are injected, so the set of pieces/geometry is configurable.

It checks shape legality (the piece's geometry reaches the target, with the path
clear — the path check lives in SlideMovement) and the capture rule (you cannot
land on your own color; an enemy at the destination is a legal capture).

Deliberately not here yet (added at this same method later):
- pawn rules (Iteration 5);
- "can't redirect a piece already moving" (Iteration 7).
"""

from __future__ import annotations

from kfchess.model.board import Board
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

        letter = piece.piece_type.letter
        if letter not in self._movement_rules:
            return False  # a piece with no movement rule can't move (e.g. pawn pre-iter5)

        if not self._movement_rules.get(letter).can_reach(source, target, board):
            return False

        # Capture rule: an empty destination is a plain move, an enemy there is a
        # legal capture, but you cannot land on a piece of your own color.
        occupant = board.piece_at(target)
        if occupant is not None and occupant.color == piece.color:
            return False
        return True
