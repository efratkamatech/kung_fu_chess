"""Tests for the shell home screen's username prompt."""

from kfchess.client.home_screen import ask_username


def canned(*answers):
    """A fake read_line that returns each answer in turn (ignores the prompt text)."""
    remaining = list(answers)

    def read_line(prompt):
        return remaining.pop(0)

    return read_line


def test_returns_the_typed_name_stripped_of_whitespace():
    assert ask_username(canned("  Efrat  ")) == "Efrat"


def test_reprompts_until_a_non_blank_name_is_given():
    assert ask_username(canned("", "   ", "Dan")) == "Dan"
