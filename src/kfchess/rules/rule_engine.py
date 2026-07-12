"""RuleEngine: read-only legality of a requested move.

Given the board and a move (source -> target), decide whether it is legal. It is
strictly read-only: it never mutates the board (that is the GameEngine's job). The
movement rules are injected, so the set of pieces/geometry is configurable.

Iteration 3 checks *shape* legality only — does the piece's movement geometry
reach the target. Deliberately not here yet (added at this same method in later
iterations):
- blockers along the path and can't-capture-own-color (Iteration 4);
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

        return self._movement_rules.get(letter).can_reach(source, target, board)
