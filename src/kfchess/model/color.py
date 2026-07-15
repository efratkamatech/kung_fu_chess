"""Color: which side a piece belongs to (white or black).

Owned by the Model layer. It knows the two sides and how each maps to its text
prefix in the fixture format (``w`` / ``b``), but nothing about movement, timing,
or rendering. The prefix strings themselves come from ``config`` so the text
vocabulary stays defined in one place.
"""

from __future__ import annotations

from enum import Enum

from kfchess.config import BLACK_PREFIX, WHITE_PREFIX


class Color(Enum):
    """A player side. The enum *value* is the fixture prefix, so ``Color('w')``
    resolves to ``Color.WHITE`` and ``Color.WHITE.value`` is ``'w'``."""

    WHITE = WHITE_PREFIX
    BLACK = BLACK_PREFIX

    @property
    def prefix(self) -> str:
        """The one-letter fixture prefix for this color (``'w'`` or ``'b'``)."""
        return self.value

    @property
    def opponent(self) -> "Color":
        """The other side — used to credit a capture to the capturing player."""
        return Color.BLACK if self is Color.WHITE else Color.WHITE

    @classmethod
    def from_prefix(cls, prefix: str) -> "Color":
        """Resolve a fixture prefix to a Color.

        Raises ``ValueError`` for an unrecognized prefix; the parser turns that
        into the appropriate validation handling rather than crashing.
        """
        return cls(prefix)
