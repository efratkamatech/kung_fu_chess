"""Tests for the Auth service: it answers the shard that asked, and remembers nothing.

The point of this service is a number — how many people can be let in per second — and
the property that delivers it is that any replica can answer any login. So the test that
matters here is the queue-group one: two replicas listening, one password checked once.
"""

from kfchess.auth.service import AuthService
from kfchess.bus import subjects
from kfchess.bus.envelope import AuthRequest, decode_auth_result, encode
from kfchess.bus.message_bus import InProcessMessageBus
from kfchess.config import START_RATING
from kfchess.server.user_store import UserStore


def an_auth(replicas=1):
    """A bus with ``replicas`` Auth services on it, all sharing one accounts store."""
    bus = InProcessMessageBus()
    users = UserStore(":memory:")
    for _ in range(replicas):
        AuthService(bus, users)
    return bus, users


def ask(bus, username="Efrat", password="pw", conn_id="gw1.0", shard_id="sh1"):
    bus.publish(
        subjects.AUTH_REQUEST,
        encode(AuthRequest(conn_id, username, password, shard_id)),
    )


def answers(bus, shard_id="sh1"):
    return [decode_auth_result(p) for p in bus.sent_to(subjects.shard_auth(shard_id))]


def test_a_first_time_username_is_registered_and_comes_back_rated():
    bus, _ = an_auth()

    ask(bus)

    assert answers(bus)[-1].rating == START_RATING
    assert answers(bus)[-1].username == "Efrat"


def test_a_wrong_password_comes_back_with_no_rating():
    """One field carries the verdict, so a flag and a number cannot disagree."""
    bus, _ = an_auth()
    ask(bus, password="secret")

    ask(bus, password="wrong")

    assert answers(bus)[-1].rating is None


def test_the_answer_goes_to_the_shard_that_asked():
    """An Auth replica has never heard of the connection; the request says where to reply."""
    bus, _ = an_auth()

    ask(bus, shard_id="sh2")

    assert answers(bus, "sh2") != []
    assert answers(bus, "sh1") == []


def test_the_answer_names_the_connection_it_is_about():
    bus, _ = an_auth()

    ask(bus, conn_id="gw7.42")

    assert answers(bus)[-1].conn_id == "gw7.42"


def test_no_password_comes_back():
    """What the shard needs to seat somebody is a name and a rating."""
    bus, _ = an_auth()

    ask(bus, password="secret")

    assert "secret" not in bus.sent_to(subjects.shard_auth("sh1"))[-1]


def test_one_login_is_checked_once_however_many_replicas_are_listening():
    """The queue group, and the whole reason this scales: shared, not multiplied."""
    bus, _ = an_auth(replicas=3)

    ask(bus)

    assert len(answers(bus)) == 1


def test_replicas_share_the_work_rather_than_one_taking_it_all():
    bus, _ = an_auth(replicas=2)

    for index in range(4):
        ask(bus, username=f"player{index}")

    assert len(answers(bus)) == 4  # each answered once, by whichever was next in turn


def test_the_accounts_are_the_same_accounts_the_shard_reads():
    """One schema, one database. Two spellings of it is how they come to disagree."""
    bus, users = an_auth()

    ask(bus, username="Efrat")

    assert users.get_rating("Efrat") == START_RATING
