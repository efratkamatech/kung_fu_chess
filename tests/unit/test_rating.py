"""Tests for the ELO rating maths."""

from kfchess.server.rating import updated_ratings


def test_equal_ratings_move_by_half_the_k_factor():
    # With equal ratings the expected score is 0.5, so the winner gains k*0.5.
    new_winner, new_loser = updated_ratings(1200, 1200, k=32)
    assert new_winner == 1216
    assert new_loser == 1184


def test_elo_is_zero_sum():
    new_winner, new_loser = updated_ratings(1300, 1100, k=32)
    assert (new_winner - 1300) == (1100 - new_loser)  # winner's gain == loser's loss


def test_beating_a_stronger_player_gains_more_than_beating_a_weaker_one():
    upset_gain = updated_ratings(1200, 1600)[0] - 1200      # weak beats strong
    expected_gain = updated_ratings(1600, 1200)[0] - 1600   # strong beats weak
    assert upset_gain > expected_gain


def test_a_heavy_favourite_barely_moves_when_it_wins():
    new_winner, _ = updated_ratings(2000, 1000, k=32)
    assert new_winner - 2000 <= 1  # almost nothing to gain against a much weaker player
