"""Tests for the shell home screen: username/password prompts and the login loop."""

from kfchess.client.home_screen import (
    ask_credentials,
    ask_username,
    lobby_loop,
    login_loop,
)
from kfchess.model.color import Color


def canned(*answers):
    """A fake read_line that returns each answer in turn (ignores the prompt text)."""
    remaining = list(answers)

    def read_line(prompt):
        return remaining.pop(0)

    return read_line


class FakeNet:
    """Records login attempts and hands back preset wait_for_login results in turn."""

    def __init__(self, results):
        self._results = list(results)
        self.attempts = []

    def login(self, username, password):
        self.attempts.append((username, password))

    def wait_for_login(self):
        return self._results.pop(0)


def test_ask_username_returns_the_typed_name_stripped():
    assert ask_username(canned("  Efrat  ")) == "Efrat"


def test_ask_username_reprompts_until_non_blank():
    assert ask_username(canned("", "   ", "Dan")) == "Dan"


def test_ask_credentials_returns_username_and_password():
    creds = ask_credentials(read_line=canned("Efrat"), read_secret=canned("secret"))
    assert creds == ("Efrat", "secret")


def test_login_loop_returns_the_username_on_first_success():
    net = FakeNet([None])  # accepted immediately
    username = login_loop(
        net, read_line=canned("Efrat"), read_secret=canned("pw"), notify=lambda m: None
    )
    assert username == "Efrat"
    assert net.attempts == [("Efrat", "pw")]


def test_login_loop_retries_after_a_bad_password():
    net = FakeNet(["bad_password", None])  # first refused, second accepted
    notes = []
    username = login_loop(
        net,
        read_line=canned("Efrat", "Efrat"),
        read_secret=canned("wrong", "right"),
        notify=notes.append,
    )
    assert username == "Efrat"
    assert net.attempts == [("Efrat", "wrong"), ("Efrat", "right")]
    assert len(notes) == 1  # one "try again" message


class LobbyNet:
    """Records Play requests and hands back preset wait_for_match results in turn."""

    def __init__(self, results):
        self._results = list(results)
        self.plays = 0

    def play(self):
        self.plays += 1

    def wait_for_match(self):
        return self._results.pop(0)


def test_lobby_loop_returns_once_seated():
    net = LobbyNet([("seated", Color.WHITE)])
    lobby_loop(net, read_line=canned(""), notify=lambda m: None)
    assert net.plays == 1


def test_lobby_loop_retries_after_no_opponent():
    net = LobbyNet([("notice", "no_opponent"), ("seated", Color.BLACK)])
    notes = []
    lobby_loop(net, read_line=canned("", ""), notify=notes.append)
    assert net.plays == 2
    assert len(notes) == 1  # one "couldn't find an opponent" message
