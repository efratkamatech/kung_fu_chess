"""ELO rating maths: how a finished game moves the two players' ratings.

Pure arithmetic, no storage — the :mod:`kfchess.server.user_store` persists the
numbers, and this only computes the new pair. ELO is zero-sum: the winner gains exactly
what the loser drops (bar rounding). How much depends on the gap: beating a
higher-rated player gains more (an upset), beating a lower-rated one gains little.
"""

from __future__ import annotations

from typing import Tuple

from kfchess.config import ELO_K


def updated_ratings(
    winner: int, loser: int, k: int = ELO_K
) -> Tuple[int, int]:
    """Return ``(new_winner, new_loser)`` after the winner beats the loser.

    ``k`` is the ELO K-factor — the maximum a single game can move a rating.
    """
    expected_winner = 1.0 / (1.0 + 10.0 ** ((loser - winner) / 400.0))
    delta = k * (1.0 - expected_winner)  # winner's gain == loser's loss
    return round(winner + delta), round(loser - delta)
