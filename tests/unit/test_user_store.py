"""Tests for UserStore: accounts, password hashing, ratings (in-memory SQLite)."""

from kfchess.config import START_RATING
from kfchess.server.user_store import UserStore


def a_store():
    return UserStore(":memory:")


def test_a_first_login_registers_the_account_at_the_starting_rating():
    store = a_store()
    assert store.register_or_login("Efrat", "secret") == START_RATING


def test_a_returning_user_with_the_right_password_logs_in():
    store = a_store()
    store.register_or_login("Efrat", "secret")
    assert store.register_or_login("Efrat", "secret") == START_RATING


def test_a_wrong_password_is_rejected():
    store = a_store()
    store.register_or_login("Efrat", "secret")
    assert store.register_or_login("Efrat", "guess") is None


def test_the_password_is_not_stored_in_the_clear():
    store = a_store()
    store.register_or_login("Efrat", "secret")
    stored = store._conn.execute("SELECT salt, pw_hash FROM users").fetchone()
    assert b"secret" not in stored[1]  # only a salted hash is kept, never the password


def test_get_and_set_rating_round_trip():
    store = a_store()
    store.register_or_login("Efrat", "secret")
    store.set_rating("Efrat", 1300)
    assert store.get_rating("Efrat") == 1300


def test_record_win_moves_both_ratings():
    store = a_store()
    store.register_or_login("Efrat", "a")   # both start at 1200
    store.register_or_login("Dan", "b")
    store.record_win("Efrat", "Dan")
    assert store.get_rating("Efrat") == 1216
    assert store.get_rating("Dan") == 1184


def test_accounts_persist_across_reopening_the_database(tmp_path):
    db = tmp_path / "users.db"
    first = UserStore(db)
    first.register_or_login("Efrat", "secret")
    first.set_rating("Efrat", 1250)
    first.close()

    reopened = UserStore(db)
    assert reopened.register_or_login("Efrat", "secret") == 1250  # survived the restart
    reopened.close()
