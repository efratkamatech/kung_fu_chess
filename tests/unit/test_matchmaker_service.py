"""Tests for the shared matchmaker: same pairing rules, one queue for every shard.

The rules are the interesting part and they are not allowed to have changed, so most of
this file is the same set of cases the single-process queue is held to — closest rating
wins, ties go to the longest waiter, the earlier arrival plays white — asked of a queue
that now lives outside the process.
"""

from kfchess.config import MATCH_ELO_RANGE, MATCH_TIMEOUT_MS
from kfchess.services.matchmaker import QUEUE, Match, Matchmaker, Waiter, wall_clock_ms
from kfchess.services.store import InMemoryKeyValueStore


def a_matchmaker(clock=None):
    """A matchmaker on a shared store, with a clock the test drives."""
    now = clock if clock is not None else [1_000_000]
    store = InMemoryKeyValueStore(lambda: now[0] / 1000)
    return Matchmaker(store, now_ms=lambda: now[0]), store, now


# --- pairing ------------------------------------------------------------------

def test_a_lone_seeker_waits():
    matchmaker, _, _ = a_matchmaker()
    assert matchmaker.seek("Efrat", 1200) is None
    assert matchmaker.is_waiting("Efrat")


def test_two_seekers_in_range_are_paired_earliest_as_white():
    matchmaker, _, _ = a_matchmaker()
    matchmaker.seek("Efrat", 1200)

    assert matchmaker.seek("Dan", 1200) == Match("Efrat", "Dan", 1200, 1200)


def test_the_paired_partner_leaves_the_queue():
    matchmaker, _, _ = a_matchmaker()
    matchmaker.seek("Efrat", 1200)
    matchmaker.seek("Dan", 1200)

    assert not matchmaker.is_waiting("Efrat")
    assert not matchmaker.is_waiting("Dan")  # and the seeker was never added


def test_a_seeker_outside_the_window_is_not_paired():
    matchmaker, _, _ = a_matchmaker()
    matchmaker.seek("Efrat", 1200)

    assert matchmaker.seek("Dan", 1200 + MATCH_ELO_RANGE + 1) is None
    assert matchmaker.is_waiting("Dan")  # both are now waiting, separately


def test_the_edge_of_the_window_still_counts():
    matchmaker, _, _ = a_matchmaker()
    matchmaker.seek("Efrat", 1200)
    assert matchmaker.seek("Dan", 1200 + MATCH_ELO_RANGE) is not None


def test_the_closest_rating_wins_whichever_side_it_is_on():
    """Note the ratings: two waiters can only coexist if they are outside *each other's*
    window, or they would have paired the moment the second one arrived. So the real
    choice is always between one above and one below -- which is exactly the pair of
    queries the search makes."""
    matchmaker, _, _ = a_matchmaker()
    matchmaker.seek("Below", 1120)      # 80 away from 1200
    matchmaker.seek("Above", 1290)      # 90 away, and 170 from Below, so they did not pair

    assert matchmaker.seek("Efrat", 1200).white == "Below"


def test_a_partner_below_is_found_as_readily_as_one_above():
    """Two queries, not one: a candidate under the seeker's rating is not invisible."""
    matchmaker, _, _ = a_matchmaker()
    matchmaker.seek("Lower", 1150)

    assert matchmaker.seek("Efrat", 1200).white == "Lower"


def test_an_exact_tie_goes_to_whoever_waited_longest():
    matchmaker, _, now = a_matchmaker()
    matchmaker.seek("First", 1140)     # 60 below 1200
    now[0] += 5_000
    matchmaker.seek("Second", 1260)    # 60 above, and 120 from First, so they did not pair

    assert matchmaker.seek("Efrat", 1200).white == "First"


def test_a_seeker_is_never_paired_with_herself():
    matchmaker, _, _ = a_matchmaker()
    matchmaker.seek("Efrat", 1200)

    assert matchmaker.seek("Efrat", 1200) is None  # pressed Play twice


# --- leaving the queue ---------------------------------------------------------

def test_cancelling_takes_a_seeker_out():
    matchmaker, _, _ = a_matchmaker()
    matchmaker.seek("Efrat", 1200)

    matchmaker.cancel("Efrat")

    assert not matchmaker.is_waiting("Efrat")
    assert matchmaker.seek("Dan", 1200) is None  # and she is not there to be matched


def test_cancelling_someone_who_is_not_waiting_is_harmless():
    matchmaker, _, _ = a_matchmaker()
    matchmaker.cancel("Efrat")
    assert not matchmaker.is_waiting("Efrat")


# --- giving up, without anybody sweeping ---------------------------------------

def test_a_waiter_who_gave_up_long_ago_is_not_matched():
    matchmaker, _, now = a_matchmaker()
    matchmaker.seek("Ghost", 1200)

    now[0] += MATCH_TIMEOUT_MS

    assert matchmaker.seek("Efrat", 1200) is None  # she waits instead, alone


def test_the_stale_entry_is_dropped_by_whoever_trips_over_it():
    """No timer and no sweep: the cost is paid by a read that was happening anyway."""
    matchmaker, store, now = a_matchmaker()
    matchmaker.seek("Ghost", 1200)
    now[0] += MATCH_TIMEOUT_MS

    matchmaker.seek("Efrat", 1200)

    assert Waiter("Ghost", 1200, 1_000_000).member not in store._rankings[QUEUE]


def test_a_live_waiter_behind_a_stale_one_is_still_found():
    """Evicting has to resume the search, not abandon it."""
    matchmaker, _, now = a_matchmaker()
    matchmaker.seek("Ghost", 1201)      # nearest to 1200, and about to go stale
    now[0] += MATCH_TIMEOUT_MS
    matchmaker.seek("Live", 1190)       # joined just now, further away

    assert matchmaker.seek("Efrat", 1200).white == "Live"


def test_a_waiter_just_short_of_the_timeout_is_still_matched():
    matchmaker, _, now = a_matchmaker()
    matchmaker.seek("Efrat", 1200)

    now[0] += MATCH_TIMEOUT_MS - 1

    assert matchmaker.seek("Dan", 1200) is not None


# --- the shape of what is stored ------------------------------------------------

def test_the_queue_is_scored_by_rating_so_the_window_is_a_score_range():
    matchmaker, store, _ = a_matchmaker()
    matchmaker.seek("Efrat", 1234)

    ranking = store._rankings[QUEUE]
    assert list(ranking.values()) == [1234]


def test_a_member_carries_when_its_waiter_joined():
    waiter = Waiter("Efrat", 1200, 1_700_000_000_000)
    assert Waiter.from_member(waiter.member, 1200) == waiter


def test_a_username_with_a_colon_in_it_still_round_trips():
    """The separator splits once, from the left: the name may contain another."""
    waiter = Waiter("odd:name", 1200, 1_700_000_000_000)
    assert Waiter.from_member(waiter.member, 1200) == waiter


def test_the_default_clock_is_the_time_of_day():
    """Two shards have to agree who waited longer, so it cannot be a per-process clock."""
    assert wall_clock_ms() > 1_700_000_000_000  # a real epoch time, not an uptime


# --- coming back after giving up ----------------------------------------------

def test_a_waiter_past_the_timeout_is_no_longer_actively_waiting():
    """Her client has stopped listening, so the server must not call her "searching"."""
    matchmaker, _, now = a_matchmaker()
    matchmaker.seek("Efrat", 1200)

    now[0] += MATCH_TIMEOUT_MS

    assert not matchmaker.is_waiting("Efrat")


def test_seeking_again_after_giving_up_replaces_the_old_entry():
    """Otherwise she is in the ranking twice, and one of them is an address she left.

    Nothing sweeps the queue, so her first entry outlives her patience. If a second seek
    simply added another, a later seeker could be paired with the stale one — and the
    removal that follows would delete the record belonging to the live one.
    """
    matchmaker, store, now = a_matchmaker()
    matchmaker.seek("Efrat", 1200)
    first_member = Waiter("Efrat", 1200, now[0]).member

    now[0] += MATCH_TIMEOUT_MS
    matchmaker.seek("Efrat", 1200)  # she pressed Play again

    assert store.first_in_range(QUEUE, 1200, 1200) == (
        Waiter("Efrat", 1200, now[0]).member,
        1200,
    )
    assert matchmaker.is_waiting("Efrat")
    matchmaker.cancel("Efrat")  # and the one record left is the one that gets removed
    assert store.first_in_range(QUEUE, 1200, 1200) is None
    assert first_member != Waiter("Efrat", 1200, now[0]).member  # it really was a new one


def test_a_player_who_came_back_is_matched_at_her_new_arrival_time():
    matchmaker, _, now = a_matchmaker()
    matchmaker.seek("Efrat", 1200)
    now[0] += MATCH_TIMEOUT_MS
    matchmaker.seek("Efrat", 1200)

    assert matchmaker.seek("Dan", 1200) == Match("Efrat", "Dan", 1200, 1200)


# --- the property a per-process queue could not have ---------------------------

def test_a_player_waiting_on_one_shard_is_found_by_a_seeker_on_another():
    """One pool, not one pool per process. This is the reason the queue moved.

    Two shards with their own dictionaries would leave these two waiting side by side
    for ever, each in a queue of one, however close their ratings.
    """
    _, store, now = a_matchmaker()
    here = Matchmaker(store, now_ms=lambda: now[0])
    there = Matchmaker(store, now_ms=lambda: now[0])

    assert here.seek("Efrat", 1200) is None  # she waits, on this shard
    now[0] += 1

    assert there.seek("Dan", 1210) == Match("Efrat", "Dan", 1200, 1210)
    assert not here.is_waiting("Efrat")  # and the shard she waited on agrees she is gone


def test_the_closest_partner_wins_across_shards_too():
    """The pairing rule is a property of the queue, not of who is asking.

    The two waiters are 149 apart, so neither pairs with the other on arrival and both
    are still there when Dan seeks between them: one 99 above him, one 50 below.
    """
    _, store, now = a_matchmaker()
    shards = [Matchmaker(store, now_ms=lambda: now[0]) for _ in range(3)]
    shards[0].seek("Far", 1299)
    now[0] += 1
    shards[1].seek("Near", 1150)
    now[0] += 1

    assert shards[2].seek("Dan", 1200) == Match("Near", "Dan", 1150, 1200)


# --- claiming, which is not the same as finding ---------------------------------

def test_removing_a_waiter_says_whether_it_was_this_caller_who_removed_her():
    """The answer that makes claiming safe: only one remover can be told 'yes'."""
    matchmaker, store, _ = a_matchmaker()
    matchmaker.seek("Efrat", 1200)
    member = Waiter("Efrat", 1200, 1_000_000).member

    assert store.remove_from_ranking(QUEUE, member) is True
    assert store.remove_from_ranking(QUEUE, member) is False


def test_a_waiter_claimed_by_somebody_else_is_not_matched_again():
    """The bug this exists to stop, found by running two shards under load.

    Two shards search at the same instant and both see the same waiting player. Both used
    to return her as a match, so she was seated in two games at once — and a player can
    only ever leave one of them, so the other stayed open for ever, held by a member who
    would never depart. Finding her is not claiming her; the removal decides.
    """
    _, store, now = a_matchmaker()
    here = Matchmaker(store, now_ms=lambda: now[0])
    there = Matchmaker(store, now_ms=lambda: now[0])
    here.seek("Efrat", 1200)  # the only person waiting

    # `there` finds her and claims her; `here` finds her a moment later and does not.
    stolen = there.seek("Dan", 1200)
    missed = here.seek("Noa", 1200)

    assert stolen == Match("Efrat", "Dan", 1200, 1200)
    assert missed is None          # nobody left to pair with...
    assert here.is_waiting("Noa")  # ...so she waits, rather than being handed a ghost


class LosesTheFirstClaim:
    """A store where the first removal loses the race, as Redis reports when it does.

    The real interleaving cannot be produced in one thread: the member has to still be
    there when the search reads it and gone when the claim tries to take it, which is a
    thing two processes do to each other. This is that moment, held still.
    """

    def __init__(self, store):
        self._store = store
        self._lost = False

    def __getattr__(self, name):
        return getattr(self._store, name)

    def remove_from_ranking(self, key, member):
        if not self._lost:
            self._lost = True
            self._store.remove_from_ranking(key, member)  # somebody else took her
            return False
        return self._store.remove_from_ranking(key, member)


def test_a_seeker_who_loses_a_claim_takes_the_next_waiter_instead():
    """The retry, exercised at the exact instant the race is lost."""
    _, store, now = a_matchmaker()
    seeded = Matchmaker(store, now_ms=lambda: now[0])
    seeded.seek("Taken", 1210)
    now[0] += 1
    seeded.seek("Free", 1390)

    racing = Matchmaker(LosesTheFirstClaim(store), now_ms=lambda: now[0])

    assert racing.seek("Dan", 1300) == Match("Free", "Dan", 1390, 1300)


def test_a_lost_claim_looks_again_rather_than_giving_up():
    """There may be somebody else waiting, and the seeker is owed a game.

    The two waiters are 180 apart so neither pairs with the other, and Dan sits 90 from
    each — a tie the longest wait breaks in favour of the one that is about to be stolen.
    """
    _, store, now = a_matchmaker()
    here = Matchmaker(store, now_ms=lambda: now[0])
    here.seek("Taken", 1210)
    joined = now[0]
    now[0] += 1
    here.seek("Free", 1390)

    # Another shard claims "Taken" between this seeker's search and its claim.
    store.remove_from_ranking(QUEUE, Waiter("Taken", 1210, joined).member)

    assert here.seek("Dan", 1300) == Match("Free", "Dan", 1390, 1300)


def test_a_waiter_whose_record_is_gone_is_not_matched():
    """A pairing nobody can deliver is worse than no pairing at all.

    The ranking says who is waiting and at what rating; her own record is the only place
    her *address* is written down. Losing it and matching her anyway hands the receiving
    shard a connection id of ``""`` — it adopts a socket that does not exist, seats her
    in a game, and nothing can ever close it, because nothing will ever report the
    departure of a connection nobody has.
    """
    matchmaker, store, now = a_matchmaker()
    matchmaker.seek("Ghost", 1200, "gw1.7", "sh1")
    store.delete("mm:seeker:Ghost")  # her record, gone; the ranking still lists her

    assert matchmaker.seek("Dan", 1200) is None
    assert not matchmaker.is_waiting("Ghost")   # the stale entry is gone...
    assert matchmaker.is_waiting("Dan")         # ...and Dan waits, rather than being lost
    assert store.first_in_range(QUEUE, 0, 9999)[0].endswith("Dan")


def test_a_reachable_waiter_behind_an_unreachable_one_is_still_matched():
    """Dropping the unaddressable one is a skip, not a surrender."""
    matchmaker, store, now = a_matchmaker()
    matchmaker.seek("Ghost", 1210, "", "")
    store.delete("mm:seeker:Ghost")
    now[0] += 1
    matchmaker.seek("Real", 1390, "gw1.9", "sh2")

    match = matchmaker.seek("Dan", 1300)

    assert match == Match("Real", "Dan", 1390, 1300, "gw1.9", "sh2")


def test_a_matched_partner_always_comes_with_an_address():
    """The property the two tests above are really defending."""
    matchmaker, _, _ = a_matchmaker()
    matchmaker.seek("Efrat", 1200, "gw1.3", "sh1")

    match = matchmaker.seek("Dan", 1200, "gw1.4", "sh1")

    assert match.white_conn_id == "gw1.3"
    assert match.white_shard_id == "sh1"
