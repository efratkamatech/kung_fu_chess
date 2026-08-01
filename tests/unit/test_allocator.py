"""Tests for the allocator: which shard runs the next game, and which shards exist.

The liveness half is the interesting one. Picking the smallest number in a sorted set is
not a design problem; knowing that the name attached to it belongs to a process that is
still running is, because nothing announces a crash. Every test about a "dead" shard here
is really a test that the pool does not have to be told.
"""

from kfchess.config import SHARD_TTL_S
from kfchess.services.allocator import POOL, Allocator
from kfchess.services.store import InMemoryKeyValueStore


def a_pool(clock=None):
    now = clock if clock is not None else [0.0]
    store = InMemoryKeyValueStore(lambda: now[0])
    return Allocator(store), store, now


def test_nothing_can_be_allocated_before_any_shard_says_it_exists():
    allocator, _, _ = a_pool()
    assert allocator.allocate() is None


def test_a_lone_shard_gets_everything():
    allocator, _, _ = a_pool()
    allocator.announce("sh1", games=0)

    assert allocator.allocate() == "sh1"


def test_the_least_loaded_shard_wins():
    allocator, _, _ = a_pool()
    allocator.announce("sh1", games=40)
    allocator.announce("sh2", games=3)
    allocator.announce("sh3", games=17)

    assert allocator.allocate() == "sh2"


def test_a_shard_that_reports_again_is_ranked_by_its_new_load():
    allocator, _, _ = a_pool()
    allocator.announce("sh1", games=1)
    allocator.announce("sh2", games=9)

    allocator.announce("sh1", games=50)  # it filled up

    assert allocator.allocate() == "sh2"


def test_allocating_does_not_itself_change_the_load():
    """The shard reports its own count; the allocator does not keep a second tally.

    Two sources for one number is how they come to disagree, and the shard is the one
    that knows — games end without anybody allocating anything.
    """
    allocator, _, _ = a_pool()
    allocator.announce("sh1", games=0)

    assert [allocator.allocate() for _ in range(3)] == ["sh1", "sh1", "sh1"]


# --- liveness: the half nobody is told about -----------------------------------

def test_a_shard_that_stopped_reporting_is_not_allocated_to():
    allocator, _, now = a_pool()
    allocator.announce("sh1", games=0)   # the emptiest, and about to die
    allocator.announce("sh2", games=30)

    now[0] = SHARD_TTL_S + 1             # sh1 said nothing more; sh2 kept going
    allocator.announce("sh2", games=30)

    assert allocator.allocate() == "sh2"


def test_a_dead_shard_is_taken_out_of_the_pool_by_whoever_finds_it():
    """Lazy, like the matchmaking queue: no reaper walking the cluster on a timer."""
    allocator, store, now = a_pool()
    allocator.announce("sh1", games=0)
    now[0] = SHARD_TTL_S + 1
    allocator.announce("sh2", games=30)

    allocator.allocate()

    assert store.first_in_range(POOL, 0, float("inf")) == ("sh2", 30)


def test_a_pool_of_nothing_but_dead_shards_answers_none():
    allocator, _, now = a_pool()
    allocator.announce("sh1", games=0)
    allocator.announce("sh2", games=1)
    now[0] = SHARD_TTL_S + 1

    assert allocator.allocate() is None


def test_a_shard_that_comes_back_is_allocated_to_again():
    allocator, _, now = a_pool()
    allocator.announce("sh1", games=0)
    now[0] = SHARD_TTL_S + 1
    allocator.allocate()  # ...and is dropped here

    allocator.announce("sh1", games=0)  # restarted

    assert allocator.allocate() == "sh1"


def test_retiring_takes_a_shard_out_at_once():
    allocator, _, _ = a_pool()
    allocator.announce("sh1", games=0)
    allocator.announce("sh2", games=5)

    allocator.retire("sh1")

    assert allocator.allocate() == "sh2"


def test_retiring_the_last_shard_leaves_nowhere_to_put_a_game():
    allocator, _, _ = a_pool()
    allocator.announce("sh1", games=0)

    allocator.retire("sh1")

    assert allocator.allocate() is None
