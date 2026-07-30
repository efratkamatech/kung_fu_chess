"""Tests for the one decision the async server entry point makes: how long to sleep.

``serve`` itself is socket and timer plumbing and is excluded from coverage; this is the
piece of it that has a right and a wrong answer, so it lives at module level and is
tested with a fake hub instead of a running event loop.
"""

from kfchess.server.game_server import next_sleep_s


class FakeHub:
    """A lobby stand-in that reports whatever the test wants its next event to be."""

    def __init__(self, due_ms):
        self._due_ms = due_ms

    def next_event_delay_ms(self):
        return self._due_ms


def test_an_idle_lobby_waits_out_the_whole_interval():
    assert next_sleep_s(FakeHub(None), 50) == 0.05


def test_a_sooner_event_pulls_the_wake_up_earlier():
    assert next_sleep_s(FakeHub(10), 50) == 0.01


def test_a_later_event_still_waits_no_longer_than_the_ceiling():
    # The resync and the matchmaking timeouts count elapsed time rather than name a
    # moment, so the loop has to come round even when no game needs it.
    assert next_sleep_s(FakeHub(20_000), 50) == 0.05


def test_an_event_that_is_already_due_does_not_sleep_at_all():
    assert next_sleep_s(FakeHub(0), 50) == 0.0
