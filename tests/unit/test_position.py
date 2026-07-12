import dataclasses

import pytest

from kfchess.model.position import Position


def test_equality_and_hashable_as_key():
    assert Position(1, 2) == Position(1, 2)
    assert Position(1, 2) != Position(2, 1)
    # Frozen + slotted -> usable as a dict key (the Board relies on this).
    cells = {Position(0, 0): "a"}
    assert cells[Position(0, 0)] == "a"


def test_translated_is_pure_offset_math():
    assert Position(1, 1).translated(2, -1) == Position(3, 0)
    original = Position(1, 1)
    original.translated(5, 5)  # returns a new Position; must not mutate original
    assert original == Position(1, 1)


def test_is_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        Position(0, 0).row = 9
