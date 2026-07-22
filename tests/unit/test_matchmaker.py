"""Tests for Matchmaker: pair close-rated seekers, time lone ones out."""

from kfchess.server.matchmaker import Match, Matchmaker


def test_first_seeker_waits_and_is_not_matched():
    mm = Matchmaker()
    assert mm.seek(1, 1200) is None
    assert mm.is_waiting(1)


def test_two_close_seekers_are_paired_first_gets_white():
    mm = Matchmaker()
    mm.seek(1, 1200)
    match = mm.seek(2, 1250)
    assert match == Match(white=1, black=2)
    assert not mm.is_waiting(1)  # the paired partner leaves the queue
    assert not mm.is_waiting(2)  # the newcomer is never enqueued when matched


def test_seeker_out_of_range_is_not_paired_both_wait():
    mm = Matchmaker(elo_range=100)
    mm.seek(1, 1200)
    assert mm.seek(2, 1400) is None  # 200 apart, outside the window
    assert mm.is_waiting(1)
    assert mm.is_waiting(2)


def test_rating_exactly_at_the_edge_of_the_window_still_pairs():
    mm = Matchmaker(elo_range=100)
    mm.seek(1, 1200)
    assert mm.seek(2, 1300) == Match(white=1, black=2)  # exactly 100 apart


def test_closest_rating_in_range_is_chosen():
    # 1105 and 1290 are 185 apart, so they do not pair with each other, but both are
    # within 100 of the 1200 newcomer -- who should take the nearer one.
    mm = Matchmaker(elo_range=100)
    mm.seek(1, 1105)  # 95 away from the newcomer
    mm.seek(2, 1290)  # 90 away -- the closest
    match = mm.seek(3, 1200)
    assert match == Match(white=2, black=3)
    assert mm.is_waiting(1)  # the farther waiter stays queued


def test_tie_on_distance_goes_to_the_longest_waiter():
    # 1100 and 1300 are 200 apart (they never pair), yet each sits exactly 100 from the
    # 1200 newcomer -- a distance tie broken in favour of the earlier arrival.
    mm = Matchmaker(elo_range=100)
    mm.seek(1, 1100)  # enqueued first
    mm.seek(2, 1300)  # enqueued second
    assert mm.seek(3, 1200) == Match(white=1, black=3)  # earliest arrival wins


def test_tick_below_timeout_keeps_waiting_and_returns_nobody():
    mm = Matchmaker(timeout_ms=60_000)
    mm.seek(1, 1200)
    assert mm.tick(59_000) == []
    assert mm.is_waiting(1)


def test_tick_past_timeout_returns_and_removes_the_waiter():
    mm = Matchmaker(timeout_ms=60_000)
    mm.seek(1, 1200)
    mm.tick(30_000)
    assert mm.tick(30_000) == [1]  # 30k + 30k reaches the 60k timeout
    assert not mm.is_waiting(1)


def test_tick_reports_every_client_that_timed_out():
    mm = Matchmaker(elo_range=0, timeout_ms=1_000)  # range 0 keeps both waiting
    mm.seek(1, 1200)
    mm.seek(2, 1300)
    assert sorted(mm.tick(1_000)) == [1, 2]


def test_cancel_removes_a_waiting_seeker():
    mm = Matchmaker()
    mm.seek(1, 1200)
    mm.cancel(1)
    assert not mm.is_waiting(1)


def test_cancel_an_unknown_client_is_a_no_op():
    mm = Matchmaker()
    mm.cancel(99)  # never queued -- must not raise
    assert not mm.is_waiting(99)
