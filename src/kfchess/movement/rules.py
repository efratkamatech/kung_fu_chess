"""MovementRuleSet: which geometry each piece type moves by.

The *data* layer of movement — a registry mapping a piece letter to a Movement
built from primitives. Adding a piece means registering its geometry here; no
engine code changes. The direction/offset tuples live here because they *are* the
registry's data.

Pawn (``P``) is deliberately not registered yet; its (direction-dependent) rules
arrive in Iteration 5. Until then a pawn has no legal move, which is correct for
Iterations 3-4 where pawns only appear as blockers.
"""

from __future__ import annotations

from typing import Dict

from kfchess.movement.primitives import Movement, OffsetMovement, SlideMovement

# Direction data (registry values, not business-logic constants).
ORTHOGONAL: tuple = ((-1, 0), (1, 0), (0, -1), (0, 1))
DIAGONAL: tuple = ((-1, -1), (-1, 1), (1, -1), (1, 1))
ALL_DIRECTIONS: tuple = ORTHOGONAL + DIAGONAL
KNIGHT_OFFSETS: tuple = (
    (-2, -1), (-2, 1), (-1, -2), (-1, 2),
    (1, -2), (1, 2), (2, -1), (2, 1),
)


class MovementRuleSet:
    """A lookup of each piece letter's movement geometry."""

    def __init__(self) -> None:
        self._by_letter: Dict[str, Movement] = {}

    def register(self, letter: str, movement: Movement) -> None:
        if letter in self._by_letter:
            raise ValueError(f"movement already registered for: {letter!r}")
        self._by_letter[letter] = movement

    def get(self, letter: str) -> Movement:
        return self._by_letter[letter]

    def __contains__(self, letter: str) -> bool:
        return letter in self._by_letter


def standard_movement_rules() -> MovementRuleSet:
    """Build the movement rules for the five standard sliding/jumping pieces."""
    rules = MovementRuleSet()
    rules.register("K", SlideMovement(ALL_DIRECTIONS, max_distance=1))
    rules.register("R", SlideMovement(ORTHOGONAL))
    rules.register("B", SlideMovement(DIAGONAL))
    rules.register("Q", SlideMovement(ALL_DIRECTIONS))
    rules.register("N", OffsetMovement(KNIGHT_OFFSETS))
    return rules
