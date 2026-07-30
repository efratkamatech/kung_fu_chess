"""Tests for the shared key-value store's fake.

Everything in S3 is tested against this, so where it differs from Redis the whole stage
would be testing a fiction. The three behaviours that matter are here: reading back what
was written, expiring on time, and refusing to overwrite a claim somebody else holds.
"""

from kfchess.services.store import InMemoryKeyValueStore, monotonic_s


def a_store(clock=None):
    """A store on a clock the test drives, so expiry needs no waiting."""
    now = clock if clock is not None else [0.0]
    return InMemoryKeyValueStore(lambda: now[0]), now


def test_a_value_reads_back():
    store, _ = a_store()
    assert store.set("room:AAAA", "sh1") is True
    assert store.get("room:AAAA") == "sh1"


def test_a_key_nobody_wrote_is_absent():
    store, _ = a_store()
    assert store.get("room:NOPE") is None


def test_deleting_forgets_it_and_deleting_again_is_harmless():
    store, _ = a_store()
    store.set("player:Efrat", "somewhere")

    store.delete("player:Efrat")
    store.delete("player:Efrat")  # her game ended twice over; still not an error

    assert store.get("player:Efrat") is None


# --- expiry: what covers a process that dies without tidying up ----------------

def test_a_key_with_a_life_survives_until_it_runs_out():
    store, now = a_store()
    store.set("player:Efrat", "in room 4", ttl_s=300)

    now[0] = 299.0
    assert store.get("player:Efrat") == "in room 4"

    now[0] = 300.0
    assert store.get("player:Efrat") is None  # nothing had to sweep it


def test_a_key_with_no_life_stays_until_something_deletes_it():
    store, now = a_store()
    store.set("forever", "here")
    now[0] = 10_000.0
    assert store.get("forever") == "here"


def test_writing_again_replaces_the_value_and_its_life():
    store, now = a_store()
    store.set("player:Efrat", "room 4", ttl_s=100)
    now[0] = 50.0
    store.set("player:Efrat", "room 9", ttl_s=100)

    now[0] = 120.0
    assert store.get("player:Efrat") == "room 9"  # the second write reset the clock


# --- claiming a name: the operation a dictionary cannot do --------------------

def test_the_first_to_claim_a_name_gets_it_and_the_second_is_told_no():
    """Two shards inventing the same room id: exactly one of them may win."""
    store, _ = a_store()

    assert store.set("room:AAAA", "sh1", unless_exists=True) is True
    assert store.set("room:AAAA", "sh2", unless_exists=True) is False
    assert store.get("room:AAAA") == "sh1"  # and the loser did not overwrite the winner


def test_a_claim_that_expired_can_be_taken_by_somebody_else():
    """A room id stranded by a crashed shard comes back into circulation by itself."""
    store, now = a_store()
    store.set("room:AAAA", "sh1", ttl_s=300, unless_exists=True)

    now[0] = 301.0

    assert store.set("room:AAAA", "sh2", unless_exists=True) is True
    assert store.get("room:AAAA") == "sh2"


def test_the_default_clock_reads_real_local_time():
    """Nothing injects a clock in a deployment; the default has to be a real one."""
    assert monotonic_s() > 0
    InMemoryKeyValueStore().set("k", "v")  # builds its own clock and does not raise
