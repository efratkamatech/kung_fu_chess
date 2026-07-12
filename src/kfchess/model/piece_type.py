"""PieceType and its registry.

A ``PieceType`` is a piece's *identity* only — its canonical letter (``K``) and a
human-readable name (``king``). It holds no movement geometry (that belongs to
the Movement layer) and no rules. This is deliberate: your design says new pieces
are *registered*, not coded, so adding a piece means registering a new PieceType
here plus a movement rule in the Movement layer — never editing engine logic.

The registry is a plain object built and injected (no global state), so tests and
future custom games can supply their own set of pieces.

Later iterations extend this file, as the design's "PieceType / Role / ActionType
registries" grouping intends:
- Iteration 9 adds a king-identity marker (king capture ends the game).
- Iteration 11 adds an ``ActionType`` registry (move vs. jump-in-place).
- The ``Role`` registry (player/spectator/referee) joins when the Access layer is built.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PieceType:
    """Immutable identity of a kind of piece."""

    letter: str  # canonical uppercase type letter, e.g. "K"
    name: str  # human-readable name, e.g. "king"


class PieceTypeRegistry:
    """A lookup of the piece types a game recognizes, keyed by canonical letter.

    Additive by design: ``register`` a new PieceType to support a new piece; no
    existing code changes. Duplicate letters are rejected so a typo can't silently
    shadow a piece.
    """

    def __init__(self) -> None:
        self._by_letter: dict[str, PieceType] = {}

    def register(self, piece_type: PieceType) -> None:
        if piece_type.letter in self._by_letter:
            raise ValueError(f"piece type already registered: {piece_type.letter!r}")
        self._by_letter[piece_type.letter] = piece_type

    def get(self, letter: str) -> PieceType:
        """Return the PieceType for ``letter``; raise ``KeyError`` if unknown.

        The parser turns an unknown letter into validation handling rather than
        letting it crash.
        """
        return self._by_letter[letter]

    def __contains__(self, letter: str) -> bool:
        return letter in self._by_letter


# The canonical starting set of pieces. This is the single place new standard
# pieces would be added; custom games can build their own registry instead.
_STANDARD_PIECES = (
    PieceType("K", "king"),
    PieceType("Q", "queen"),
    PieceType("R", "rook"),
    PieceType("B", "bishop"),
    PieceType("N", "knight"),
    PieceType("P", "pawn"),
)


def standard_piece_types() -> PieceTypeRegistry:
    """Build a registry populated with the six standard chess piece types."""
    registry = PieceTypeRegistry()
    for piece_type in _STANDARD_PIECES:
        registry.register(piece_type)
    return registry
